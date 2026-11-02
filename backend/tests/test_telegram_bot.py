"""Telegram conversations against a fake Telegram client; the real pipeline and database run underneath."""
from __future__ import annotations

import dataclasses
import logging
from datetime import timedelta
from pathlib import Path

import httpx
import pytest

from app import models
from app.db import SessionLocal
from app.providers.base import SpeechResult, TranscriptionResult
from app.services import telegram_bot as tb
from app.services.pipeline import utcnow

CHAT = 555
AUDIO = Path(__file__).resolve().parent.parent / "data" / "audio"


class FakeClient:
    def __init__(self):
        self.sent: list[dict] = []
        self.voices: list[bytes] = []
        self.files: dict[str, bytes] = {}

    def send_message(self, chat_id, text, reply_markup=None):
        self.sent.append({"chat": chat_id, "text": text, "markup": reply_markup})

    def send_voice(self, chat_id, ogg):
        self.voices.append(ogg)

    def download_file(self, file_id):
        return self.files[file_id]

    @property
    def last(self) -> str:
        return self.sent[-1]["text"]


@pytest.fixture()
def rig(client):  # `client` resets the database
    fake = FakeClient()
    bot = tb.TelegramBot(fake, followup_interval_s=60, max_attempts=3, voice_replies=False)
    db = SessionLocal()
    yield bot, fake, db
    db.close()


_next_update = iter(range(1, 100000))


def message(**fields):
    return {"update_id": next(_next_update), "message": {"chat": {"id": CHAT, "type": "private"},
                                                         "from": {"language_code": "en"}, **fields}}


def say(rig, text):
    bot, _, db = rig
    bot.handle_update(db, message(text=text))


def conversation(db) -> models.TelegramConversation:
    db.expire_all()
    return tb.TelegramBot._current(db, CHAT)


def report_of(db) -> models.Report:
    return db.get(models.Report, conversation(db).report_id)


def test_start_warns_this_is_not_an_emergency_service(rig):
    say(rig, "/start")
    assert "not an official emergency service" in rig[1].last and "112" in rig[1].last


def test_complete_first_message_needs_no_follow_up(rig):
    say(rig, "Flood in Nandwadi, 25 people are stuck on the roof")
    conv, rep = conversation(rig[2]), report_of(rig[2])
    assert conv.state == "complete" and conv.next_followup_at is None
    assert rep.source == "telegram" and rep.status == "processed" and rep.follow_up_status == "answered"
    assert "Nandwadi" in rig[1].last and "25" in rig[1].last and rep.id in rig[1].last
    assert "does not guarantee" in rig[1].last


def test_each_missing_field_is_asked_one_at_a_time(rig):
    bot, fake, db = rig
    say(rig, "Please help us, water is rising fast and people are trapped")
    assert conversation(db).pending_field == "location_missing"
    assert fake.last.count("?") == 1 and "Your message has been received" in fake.last
    buttons = [b for row in fake.sent[-1]["markup"]["keyboard"] for b in row]
    assert any(b.get("request_location") for b in buttons)

    say(rig, "Nandwadi")
    assert report_of(db).extraction_current["location"]["place_id"] == "P01"
    assert conversation(db).pending_field in ("disaster_unknown", "people_unknown")


def test_full_slot_filling_with_bare_answers(rig):
    bot, fake, db = rig
    say(rig, "Please help, people are trapped here")
    say(rig, "Kesarwadi")  # not in the reference list
    assert report_of(db).extraction_current["location"]["status"] == "unmapped"
    assert conversation(db).pending_field == "disaster_unknown"
    say(rig, "flood")
    assert conversation(db).pending_field == "people_unknown"
    say(rig, "25")
    conv, rep = conversation(db), report_of(db)
    assert conv.state == "complete"
    assert rep.extraction_current["people_affected"]["count"] == 25
    assert rep.extraction_current["disaster_type"] == "flood"
    assert rep.extraction_original["people_affected"]["count"] is None  # the first version is preserved


def test_hindi_number_word_answer(rig):
    bot, _, db = rig
    bot.handle_update(db, message(text="नंदवाडी में बाढ़ आ गई है, लोग फंसे हैं", **{"from": {"language_code": "hi"}}))
    assert conversation(db).pending_field == "people_unknown"
    bot.handle_update(db, message(text="पच्चीस"))
    assert report_of(db).extraction_current["people_affected"]["count"] == 25


def test_shared_location_answers_the_location_question_with_exact_coordinates(rig):
    bot, fake, db = rig
    say(rig, "Flood here, 10 people are trapped")
    assert conversation(db).pending_field == "location_missing"
    bot.handle_update(db, message(location={"latitude": 19.076, "longitude": 72.8777, "horizontal_accuracy": 12.5}))
    conv, rep = conversation(db), report_of(db)
    assert conv.state == "complete"
    assert rep.caller_latitude == 19.076 and rep.caller_location_accuracy_m == 12.5
    incident = rep.auto_incident_id
    inc = db.get(models.Incident, incident)
    assert inc.location_status == "caller_gps"
    assert (inc.latitude, inc.longitude) == (19.076, 72.8777)
    assert inc.location["gps_accuracy_m"] == 12.5


def test_location_before_description_is_kept(rig):
    bot, _, db = rig
    bot.handle_update(db, message(location={"latitude": 18.5, "longitude": 73.8}))
    assert conversation(db).report_id is None
    say(rig, "Flood here, 10 people are trapped")
    conv, rep = conversation(db), report_of(db)
    assert rep.caller_latitude == 18.5 and conv.state == "complete"


def test_coordinates_survive_reprocessing(rig):
    bot, _, db = rig
    bot.handle_update(db, message(location={"latitude": 18.5, "longitude": 73.8}))
    say(rig, "Flood here, people are trapped")
    say(rig, "12")
    rep = report_of(db)
    assert rep.extraction_current["caller_gps"]["latitude"] == 18.5
    assert db.get(models.Incident, rep.auto_incident_id).location_status == "caller_gps"


def test_gps_incident_api_is_marked_not_simulated(rig, client):
    bot, _, db = rig
    bot.handle_update(db, message(location={"latitude": 18.5, "longitude": 73.8}))
    say(rig, "Flood here, 10 people are trapped")
    body = client.get(f"/api/incidents/{report_of(db).auto_incident_id}").json()
    assert body["coordinates_are_simulated"] is False
    assert body["location"]["coordinate_source"] == "caller_gps"
    assert "may not be the incident site" in body["recommended_action"]


def test_dont_know_moves_on_and_is_not_asked_again(rig):
    bot, fake, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")
    assert conversation(db).pending_field == "people_unknown"
    say(rig, "Don't know")
    conv = conversation(db)
    assert conv.state == "complete" and "people_unknown" in conv.skipped_fields
    assert report_of(db).extraction_current["people_affected"]["count"] is None  # stays unknown, not zero
    assert "not known" in fake.last


def test_useless_answers_stop_after_max_attempts(rig):
    bot, _, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")
    for _ in range(3):
        say(rig, "hmm")
    assert conversation(db).state == "complete"
    assert "people_unknown" in conversation(db).skipped_fields


def test_no_answer_triggers_reminders_then_stops(rig):
    bot, fake, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")
    question = fake.last
    before = len(fake.sent)
    assert bot.send_due_followups(db) == 0  # not due yet

    later = utcnow() + timedelta(seconds=61)
    assert bot.send_due_followups(db, later) == 1
    assert len(fake.sent) == before + 1 and "We still need this" in fake.last
    assert "How many people" in fake.last and "How many people" in question

    later += timedelta(seconds=61)
    assert bot.send_due_followups(db, later) == 1 and "We still need this" in fake.last

    later += timedelta(seconds=61)
    assert bot.send_due_followups(db, later) == 1
    conv = conversation(db)
    assert conv.state == "incomplete" and conv.next_followup_at is None and "stop asking" in fake.last
    assert report_of(db).follow_up_status == "unanswered"
    assert bot.send_due_followups(db, later + timedelta(days=1)) == 0  # never nags again


def test_answering_cancels_the_pending_reminder(rig):
    bot, _, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")
    say(rig, "25")
    assert bot.send_due_followups(db, utcnow() + timedelta(days=1)) == 0


def test_reply_after_giving_up_still_counts(rig):
    bot, _, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")
    later = utcnow()
    for _ in range(3):
        later += timedelta(seconds=61)
        bot.send_due_followups(db, later)
    assert conversation(db).state == "incomplete"
    say(rig, "25")
    assert report_of(db).extraction_current["people_affected"]["count"] == 25


def test_voice_note_goes_through_speech_to_text(rig):
    bot, fake, db = rig
    fake.files["v1"] = (AUDIO / "syn-006.wav").read_bytes()  # the offline mock recognises bundled audio
    bot.handle_update(db, message(voice={"file_id": "v1", "duration": 9}))
    rep = report_of(db)
    assert rep.status == "processed" and rep.transcript_provider == "mock-fixture-lookup"
    assert rep.audio_files[0].kind == "caller_audio"


def test_unreadable_voice_asks_for_text_then_recovers(rig):
    bot, fake, db = rig
    fake.files["v1"] = b"OggS" + b"\0" * 200  # unknown audio: the offline mock can't read it
    bot.handle_update(db, message(voice={"file_id": "v1", "duration": 5}))
    assert conversation(db).state == "needs_text" and "couldn't understand" in fake.last
    say(rig, "Flood in Nandwadi, 25 people are stuck")
    conv, rep = conversation(db), report_of(db)
    assert conv.state == "complete" and rep.status == "processed" and rep.extraction_current["people_affected"]["count"] == 25
    assert db.query(models.Report).count() == 1  # the same report, not a second one


def test_long_voice_note_is_rejected_before_download(rig):
    bot, fake, db = rig
    bot.handle_update(db, message(voice={"file_id": "missing", "duration": 45}))
    assert "under 30 seconds" in fake.last


def test_follow_up_voice_answer_is_transcribed_and_kept(rig, monkeypatch):
    bot, fake, db = rig
    say(rig, "Flood in Nandwadi, people are trapped")

    class FakeSTT:
        def transcribe(self, _path, mime, language):
            assert mime == "audio/ogg" and language == "en"
            return TranscriptionResult(transcript="twenty five", provider="fake", mode="mock")

    monkeypatch.setattr(tb, "get_stt", lambda _mode: FakeSTT())
    fake.files["v2"] = b"OggS" + b"\0" * 200
    bot.handle_update(db, message(voice={"file_id": "v2", "duration": 3}))
    rep = report_of(db)
    assert rep.extraction_current["people_affected"]["count"] == 25
    assert [a.kind for a in rep.audio_files] == ["caller_followup"]


def test_small_talk_does_not_create_a_report(rig):
    say(rig, "hi")
    assert conversation(rig[2]).report_id is None and "what happened" in rig[1].last
    assert rig[2].query(models.Report).count() == 0


def test_language_button_changes_the_questions(rig):
    bot, fake, db = rig
    say(rig, "हिंदी")
    assert conversation(db).language == "hi" and conversation(db).language_locked
    say(rig, "Flood in Nandwadi, people are trapped")
    assert "कितने लोग" in fake.last


def test_old_finished_conversation_starts_a_new_report(rig):
    bot, _, db = rig
    say(rig, "Flood in Nandwadi, 25 people are stuck")
    first = conversation(db)
    first_report = first.report_id
    say(rig, "Also 2 are injured here")
    assert conversation(db).report_id == first_report  # soon after: same report

    conversation(db).updated_at = utcnow() - timedelta(hours=2)
    db.commit()
    say(rig, "Fire in Kothale, 5 people are trapped")
    assert conversation(db).report_id != first_report


def test_groups_and_unlisted_chats_are_ignored(rig):
    bot, fake, db = rig
    bot.handle_update(db, {"update_id": 1, "message": {"chat": {"id": 1, "type": "group"}, "text": "flood"}})
    limited = dataclasses.replace(bot, allowed_chat_ids=frozenset({999}))
    limited.handle_update(db, message(text="Flood in Nandwadi, 25 people are stuck"))
    assert fake.sent == [] and db.query(models.Report).count() == 0


def test_voice_questions_are_reused_so_reminders_cost_no_credits(rig, monkeypatch):
    bot, fake, db = rig
    bot = dataclasses.replace(bot, voice_replies=True)
    calls = []

    class FakeTTS:
        def synthesize(self, text, language):
            calls.append(text)
            return SpeechResult(audio=b"wav", content_type="audio/wav", provider="p", mode="real", voice="v", language_code="en-IN")

    monkeypatch.setattr(tb, "get_tts", lambda _mode: FakeTTS())
    monkeypatch.setattr(tb, "wav_to_ogg_opus", lambda _wav: b"ogg")
    bot.handle_update(db, message(text="Flood in Nandwadi, people are trapped"))
    later = utcnow() + timedelta(seconds=61)
    bot.send_due_followups(db, later)
    later += timedelta(seconds=61)
    bot.send_due_followups(db, later)
    assert len(fake.voices) == 3 and len(calls) == 2  # ack + question, then one cached reminder


def test_voice_failure_never_blocks_the_text(rig, monkeypatch):
    bot, fake, db = rig
    bot = dataclasses.replace(bot, voice_replies=True)

    class BrokenTTS:
        def synthesize(self, *_a):
            raise tb.ProviderError("Timbre HTTP 500")

    monkeypatch.setattr(tb, "get_tts", lambda _mode: BrokenTTS())
    bot.handle_update(db, message(text="Flood in Nandwadi, people are trapped"))
    assert "How many people" in fake.last and fake.voices == []


def test_wav_is_converted_to_a_telegram_voice_note():
    ogg = tb.wav_to_ogg_opus((AUDIO / "syn-006.wav").read_bytes())
    assert ogg and ogg[:4] == b"OggS" and b"OpusHead" in ogg[:200]


def test_wav_with_timbre_placeholder_sizes_converts():
    wav = bytearray((AUDIO / "syn-006.wav").read_bytes())
    i = wav.find(b"data")
    wav[4:8] = b"\xff\xff\xff\xff"
    wav[i + 4:i + 8] = b"\xff\xff\xff\xff"
    assert tb.wav_to_ogg_opus(bytes(wav))[:4] == b"OggS"


def test_garbage_audio_returns_none_instead_of_raising():
    assert tb.wav_to_ogg_opus(b"not audio") is None


# ---- client: the token must never leak ------------------------------------------------
TOKEN = "123456:SECRET-TOKEN-VALUE"


def _client(handler):
    return tb.TelegramClient(TOKEN, "https://tg.test", transport=httpx.MockTransport(handler))


def test_client_sends_to_the_right_method_and_downloads():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        if request.url.path.endswith("/getFile"):
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "voice/a.ogg"}})
        if "/file/" in request.url.path:
            return httpx.Response(200, content=b"OggS")
        return httpx.Response(200, json={"ok": True, "result": {"username": "aapda_bot"}})

    c = _client(handler)
    assert c.get_me()["username"] == "aapda_bot" and c.download_file("id") == b"OggS"
    assert seen[0] == f"/bot{TOKEN}/getMe" and seen[-1] == f"/file/bot{TOKEN}/voice/a.ogg"


@pytest.mark.parametrize("handler", [
    lambda _r: httpx.Response(401, json={"ok": False, "description": "Unauthorized"}),
    lambda _r: httpx.Response(500, text="oops"),
    lambda r: (_ for _ in ()).throw(httpx.ConnectError(f"failed {r.url}")),
])
def test_errors_never_contain_the_token(handler):
    with pytest.raises(tb.TelegramError) as info:
        _client(handler).get_me()
    assert "SECRET" not in str(info.value) and info.value.__cause__ is None


def test_http_library_does_not_log_token_urls():
    import app.main  # noqa: F401  (configures logging)
    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING


def test_token_is_not_in_settings_repr_or_health(client, monkeypatch):
    from app import config
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert "SECRET" not in repr(config.load_settings())
    body = client.get("/api/health").json()
    assert body["telegram"]["configured"] is False and "SECRET" not in str(body)


def test_demo_reset_clears_conversations(rig, client):
    say(rig, "Flood in Nandwadi, 25 people are stuck")
    assert client.post("/api/demo/reset", json={}).status_code == 200
    assert conversation(rig[2]) is None


def test_dashboard_api_shows_the_record_being_collected_without_the_chat_id(rig, client):
    _, _, db = rig
    say(rig, "Please help us, water is rising fast and people are trapped")
    report = report_of(db)

    listed = client.get("/api/reports", params={"source": "telegram"}).json()
    assert [r["id"] for r in listed["items"]] == [report.id]
    assert client.get("/api/reports", params={"source": "upload"}).json()["items"] == []

    detail = client.get(f"/api/reports/{report.id}").json()
    assert detail["source"] == "telegram"
    assert detail["telegram"]["state"] == "collecting"
    assert detail["telegram"]["pending_field"] == "location_missing"
    assert "chat_id" not in detail["telegram"]
    assert detail["caller_location"] is None


def test_dashboard_api_returns_shared_coordinates(rig, client):
    bot, _, db = rig
    say(rig, "Please help us, water is rising fast and people are trapped")
    bot.handle_update(db, message(location={"latitude": 18.5, "longitude": 73.8, "horizontal_accuracy": 20.0}))
    detail = client.get(f"/api/reports/{report_of(db).id}").json()
    assert detail["caller_location"] == {"latitude": 18.5, "longitude": 73.8, "accuracy_m": 20.0}


def test_reports_outside_telegram_have_no_conversation(client):
    created = client.post("/api/reports", json={"transcript": "Flood in Nandwadi", "process": False}).json()
    assert created["telegram"] is None and created["caller_location"] is None
