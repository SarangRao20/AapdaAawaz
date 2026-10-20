"""Rule-based extraction: unknowns stay unknown, locations are never invented."""
from app.services.extraction import extract


def test_hero_report_fields():
    r = extract("Hello, main Nandwadi gaon se bol raha hoon, yahan baadh aa gayi hai. Zilla Parishad school ki "
                "chhat par hum lagbhag pachees log phase hain. Saath mein chhote bacche aur do buzurg hain. "
                "Boat bhejo, jaldi madad karo please!", "mixed")
    assert r.disaster_type == "flood"
    assert r.location.place_id == "P01" and r.location.landmark_id == "L01"
    assert r.location.source == "simulated" and r.location.latitude is not None
    assert r.people_affected.count == 25 and r.people_affected.approximate
    assert r.vulnerable_people.elderly.count == 2
    assert r.vulnerable_people.children is not None
    assert r.vulnerable_people.infants is None  # not mentioned -> unknown, not "none"
    assert {"trapped", "on_roof"} <= set(r.reported_danger)
    assert "rescue_evacuation" in r.immediate_needs
    assert r.language == "mixed"
    assert r.provider_mode == "rule_based"


def test_missing_information_stays_unknown():
    r = extract("[शोर] ... हम ... पानी ... [अस्पष्ट] ... बचाओ ... बचाओ ... [अस्पष्ट]", "hi")
    assert r.location.status == "missing" and r.location.latitude is None
    assert r.people_affected.count is None
    assert r.medical_emergency is None  # not mentioned is not "False"
    assert r.transcript_quality == "low"
    assert r.requires_human_review


def test_generic_landmark_is_ambiguous_without_coordinates():
    r = extract("मोठ्या पुलाजवळ एक गाडी पुराच्या पाण्यात वाहून गेली, आत दोन लोक होते. कोणते गाव ते माहीत नाही.", "mr")
    assert r.location.status == "ambiguous"
    assert r.location.latitude is None and r.location.place_id is None
    assert set(r.location.candidates) == {"P04", "P06", "P08"}
    assert "swept_away" in r.reported_danger
    assert r.people_affected.count == 2


def test_two_places_are_conflicting_not_guessed():
    r = extract("आम्ही नंदवाडीहून कोठाळेकडे निघालो होतो. रस्त्यात ट्रॅक्टर पुराच्या पाण्यात अडकला, "
                "आम्ही सहा जण ट्रॅक्टरवर अडकलो आहोत.", "mr")
    assert r.location.status == "conflicting"
    assert r.location.latitude is None
    assert set(r.location.candidates) == {"P01", "P02"}


def test_place_outside_reference_is_unmapped():
    r = extract("Kesarwadi gaon mein 15 log phase hain, do ghar gir gaye hain.", "mixed")
    assert r.location.status == "unmapped"
    assert r.location.place_name == "Kesarwadi"
    assert r.location.latitude is None and r.location.source == "caller_stated"


def test_families_are_not_converted_to_people():
    r = extract("कोठाले ग्राम पंचायत में पचास परिवार ठहरे हैं। पीने का पानी खत्म हो रहा है, कोई घायल नहीं है।", "hi")
    assert r.people_affected.count is None
    assert r.people_affected.families == 50
    assert "injured" not in r.reported_danger  # negated
    assert any(e.field == "danger.injured" and e.negated for e in r.evidence)
    assert r.immediate_needs == ["drinking_water"]


def test_vague_quantity_is_unknown():
    r = extract("नंदवाडी गांव में स्कूल की छत पर बहुत सारे लोग फंसे हुए हैं, बच्चे भी हैं।", "hi")
    assert r.people_affected.count is None
    assert any("Vague quantity" in u for u in r.uncertainties)


def test_range_uses_upper_bound_and_lower_confidence():
    r = extract("नंदवाडीतील जिल्हा परिषद शाळेच्या छतावर वीस ते पंचवीस लोक अडकले आहेत.", "mr")
    assert r.people_affected.count == 25
    assert r.people_affected.range == [20, 25]
    assert r.people_affected.confidence < 0.85


def test_negated_injury_in_english():
    r = extract("Small landslide on the road near Bhivgad, the road is blocked but no one is hurt.", "en")
    assert r.disaster_type == "landslide"
    assert "injured" not in r.reported_danger
    assert "road_blocked" in r.reported_danger


def test_earthquake_word_is_not_hunger():
    r = extract("भिवगड में भूकंप आया, एक घर गिर गया है और एक बूढ़ी अम्मा मलबे में दबी हुई हैं।", "hi")
    assert r.disaster_type == "earthquake"
    assert "food" not in r.immediate_needs
    assert r.vulnerable_people.elderly is not None


def test_age_mention_marks_elderly():
    r = extract("रानवाडी बाजार के पास मेरे पिताजी को इंसुलिन चाहिए, वो 72 साल के हैं।", "hi")
    assert r.vulnerable_people.elderly is not None
    assert r.critical_medication is True
    assert r.people_affected.count is None  # an age is not a head count


def test_language_detection():
    assert extract("सोनारवाडीत पाण्याच्या टाकीजवळ आठ लोक अडकले आहेत. लवकर या.", None).language == "mr"
    assert extract("सोनारवाडी में पानी की टंकी के पास चालीस लोग फंसे हैं, जल्दी बचाइए।", None).language == "hi"
    assert extract("There was a landslide at Ambeghat near the bus stand.", None).language == "en"
