"""Voice alerts: fixed wording, a person presses send, and each chat hears its own language."""
from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app import models
from app.db import SessionLocal
from app.main import app
from app.providers.base import ProviderError, SpeechResult
from app.services import voice_alerts as va
from tests.conftest import wait_for

WAV = b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x80\x3e\x00\x00\x00\x7d\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00"


class FakeTelegram:
    def __init__(self):
        self.messages, self.voices = [], []
        self.fail_for: set[int] = set()

    def send_message(self, chat_id, text, reply_markup=None):
        if chat_id in self.fail_for:
            raise va.TelegramError("blocked")
        self.messages.append((chat_id, text))

    def send_voice(self, chat_id, ogg):
        self.voices.append(chat_id)


class FakeTTS:
    calls: list[tuple[str, str]] = []

    def synthesize(self, text, language):
        FakeTTS.calls.append((text, language))
        return SpeechResult(audio=WAV, content_type="audio/wav", provider="fake", mode="mock", voice="v", language_code=language)


@pytest.fixture()
def rig(client, monkeypatch):
    fake = FakeTelegram()
    FakeTTS.calls = []
    va._speak_cached.cache_clear()
    monkeypatch.setattr(va, "settings", dataclasses.replace(va.settings, telegram_bot_token="123:abc"))
    monkeypatch.setattr(va, "telegram_client", lambda: fake)
    monkeypatch.setattr(va, "get_tts", lambda mode=None: FakeTTS())
    monkeypatch.setattr(va, "wav_to_ogg_opus", lambda wav: b"OggS")
    yield client, fake
    va._speak_cached.cache_clear()


def incident_with_chats(client, *chats: tuple[int, str]) -> str:
    rep = wait_for(client, client.post("/api/reports", json={
        "transcript": "Flood in Nandwadi, 25 people are stuck on the roof", "language_hint": "en", "process": True}).json()["id"])
    with SessionLocal() as db:
        for chat_id, language in chats:
            db.add(models.TelegramConversation(chat_id=chat_id, language=language, report_id=rep["id"], state="complete"))
        db.commit()
    return rep["incident_id"]


def test_each_chat_gets_its_own_language_with_the_place_filled_in(rig):
    client, fake = rig
    incident = incident_with_chats(client, (111, "mr"), (222, "en"))
    result = client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "move_to_high_ground", "reviewer": "dispatcher"}).json()
    assert result == {"sent": 2, "failed": 0, "voice": 2, "languages": ["en", "mr"]}
    words = dict(fake.messages)
    assert "Nandwadi" in words[111] and "सूचना" in words[111]
    assert "Nandwadi" in words[222] and "Notice" in words[222]
    assert sorted(fake.voices) == [111, 222]


def test_every_template_exists_in_every_language_and_points_to_112_without_promising_rescue(rig):
    for template in va.TEMPLATES.values():
        assert set(template["text"]) == set(va.LANGUAGES)
        for text in template["text"].values():
            assert "{place}" in text and "112" in text
    english = " ".join(t["text"]["en"].lower() for t in va.TEMPLATES.values())
    for promise in ("help is coming", "on the way", "will arrive", "rescue team"):
        assert promise not in english


def test_nothing_is_sent_when_nobody_from_this_incident_used_telegram(rig):
    client, fake = rig
    incident = incident_with_chats(client)
    result = client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "avoid_the_area", "reviewer": "d"}).json()
    assert result["sent"] == 0 and fake.messages == []


def test_a_failed_chat_does_not_stop_the_others_and_is_counted(rig):
    client, fake = rig
    incident = incident_with_chats(client, (111, "hi"), (222, "en"))
    fake.fail_for = {111}
    result = client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "avoid_the_area", "reviewer": "d"}).json()
    assert result["sent"] == 1 and result["failed"] == 1 and [c for c, _ in fake.messages] == [222]


def test_words_still_arrive_when_timbre_fails(rig, monkeypatch):
    client, fake = rig
    incident = incident_with_chats(client, (111, "en"))

    class BrokenTTS:
        def synthesize(self, text, language):
            raise ProviderError("Timbre: down")

    monkeypatch.setattr(va, "get_tts", lambda mode=None: BrokenTTS())
    result = client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "avoid_the_area", "reviewer": "d"}).json()
    assert result["sent"] == 1 and result["voice"] == 0 and len(fake.messages) == 1


def test_sending_is_audited_with_who_sent_it(rig):
    client, _ = rig
    incident = incident_with_chats(client, (111, "en"))
    client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "avoid_the_area", "reviewer": "Asha"})
    with SessionLocal() as db:
        entry = db.query(models.AuditLog).filter_by(entity_id=incident, action="voice_alert_sent").one()
    assert entry.actor == "Asha"


def test_preview_returns_audio_and_reuses_it(rig):
    client, _ = rig
    incident = incident_with_chats(client, (111, "en"))
    for _ in range(2):
        response = client.get(f"/api/incidents/{incident}/alerts/preview", params={"template": "avoid_the_area", "language": "mr"})
        assert response.status_code == 200 and response.headers["content-type"].startswith("audio/")
    assert len(FakeTTS.calls) == 1 and FakeTTS.calls[0][1] == "mr"


def test_templates_list_shows_recipients_without_revealing_chat_ids(rig):
    client, _ = rig
    incident = incident_with_chats(client, (987654321, "mr"), (222, "en"))
    response = client.get(f"/api/incidents/{incident}/alerts")
    body = response.json()
    assert body["recipients"] == {"total": 2, "languages": {"en": 1, "mr": 1}}
    assert "Nandwadi" in body["templates"][0]["text"]["hi"]
    assert "987654321" not in response.text


def test_unknown_template_is_refused(rig):
    client, _ = rig
    incident = incident_with_chats(client, (111, "en"))
    assert client.post(f"/api/incidents/{incident}/alerts/send", json={"template": "nope", "reviewer": "d"}).status_code == 400
    assert client.get(f"/api/incidents/{incident}/alerts/preview", params={"template": "nope", "language": "en"}).status_code == 400


def test_alerts_need_a_login(rig):
    client, fake = rig
    incident = incident_with_chats(client, (111, "en"))
    assert TestClient(app).post(f"/api/incidents/{incident}/alerts/send", json={"template": "avoid_the_area", "reviewer": "x"}).status_code == 401
    assert fake.messages == []
