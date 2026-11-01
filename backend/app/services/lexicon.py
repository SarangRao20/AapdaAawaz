"""Multilingual (Marathi / Hindi / romanised Hinglish / English) keyword lexicon for the
deterministic rule-based extractor.

This lexicon is intentionally small and transparent. It was written together with the
synthetic dataset, so evaluation numbers on that dataset are optimistic (see
docs/EVALUATION.md). See text_utils for the ``*`` prefix syntax.
"""
from __future__ import annotations

DISASTER_KEYWORDS: dict[str, list[str]] = {
    "flood": [
        "पूर", "पुरा*", "पूरग्रस्त*", "बाढ*", "baadh", "flood*", "paani*", "pani*",
        "पाणी भरल*", "पानी भर*", "paani bhar*", "pani bhar*", "पाणी शिरल*", "पानी घुस*",
        "नदीचे पाणी", "nadi ka paani", "पाणी वाढत*", "पानी बढ*", "पाण्याने वेढ*", "पानी से घिर*",
    ],
    "landslide": ["दरड*", "भूस्खलन*", "landslide*", "pahad gir*", "पहाड गिर*", "डोंगर कोसळ*", "mudslide*"],
    "earthquake": ["भूकंप*", "bhukamp*", "bhookamp*", "earthquake*", "tremor*", "धक्के", "zameen hil*", "जमीन हिल*"],
    "fire": ["आग", "आगी*", "aag", "fire", "शॉर्ट सर्किट*", "short circuit", "धुआं*", "smoke"],
}
DISASTER_TIEBREAK = ["fire", "earthquake", "landslide", "flood"]

DANGER_KEYWORDS: dict[str, list[str]] = {
    "trapped": ["अडक*", "फंस*", "फसे", "फसी", "फसा", "phas*", "phans*", "fase", "fasi", "fanse",
                "trapped", "stuck", "स्टक*", "stranded", "बाहेर पडता येत नाही", "निकल नहीं पा*"],
    "surrounded_by_water": ["वेढ*", "चारों तरफ", "चारो तरफ", "घिरे", "घिर गय*", "ghire", "surrounded", "चोहोबाजूंनी"],
    "on_roof": ["छतावर*", "छप्परावर*", "पत्र्यावर*", "छत पर", "छत पे", "chhat par", "chhat pe", "chat par", "roof*"],
    "water_rising": ["पाणी वाढत*", "पानी बढ*", "badh raha", "badh rahi", "बढ रहा", "rising", "वाढत आहे"],
    "flooding_inside_home": ["पाणी घरात", "घरात पाणी", "पाणी शिरल*", "पानी घुस*", "घरों में पानी", "ghar mein paani",
                             "ghar ke andar", "घर के अंदर पानी", "entered the house*", "water inside", "inside the house*",
                             "feet paani", "feet water", "foot water", "water level"],
    "swept_away": ["वाहून*", "बह गय*", "बह गई", "बह गए", "beh gay*", "bah gay*", "swept away", "washed away"],
    "drowning": ["बुडत*", "बुडाल*", "डूब*", "doob*", "drown*"],
    "structure_collapse": ["कोसळ*", "ढासळ*", "गिर गय*", "गिर गई", "गिर गए", "gir gay*", "collapsed", "collapse", "ढह*",
                           "crack*", "cracking", "shaking", "trembling", "tilting"],
    "under_debris": ["ढिगाऱ्या*", "ढिगार*", "मलबे में", "मलबे के नीचे", "दब*", "debris", "rubble", "malbe mein", "dabe", "dabi"],
    "injured": ["जखमी*", "घायल*", "ghayal", "injured", "injury", "injuries", "hurt", "चोट*", "भाजल*", "जल गय*", "burn*"],
    "unconscious": ["बेशुद्ध*", "बेहोश*", "behosh", "unconscious", "drowsy", "not responding"],
    "active_fire": ["आग लाग*", "आग लगी", "aag lag*", "fire broke", "on fire", "आगीत"],
    "missing_person": ["बेपत्ता*", "लापता*", "laapata", "lapata", "missing"],
    "road_blocked": ["रस्ता बंद", "रास्ता बंद", "पूर्ण बंद", "road band", "road is blocked", "road blocked", "blocked",
                    "queued", "queue", "vehicles stuck", "stuck behind"],
}
# Explicit immediate-threat-to-life indicators (see priority engine).
LIFE_THREAT_DANGERS = {
    "trapped", "surrounded_by_water", "on_roof", "swept_away", "drowning", "under_debris",
    "unconscious", "active_fire", "missing_person",
}
ESCALATING_DANGERS = {"water_rising", "flooding_inside_home", "structure_collapse"}

MEDICAL_EMERGENCY_KEYWORDS = [
    "बेशुद्ध*", "बेहोश*", "behosh", "unconscious", "drowsy",
    "प्रसूती*", "प्रसव*", "delivery case", "delivery", "labour pain*", "labor pain*", "डिलीवरी*",
    "भाजल*", "जल गय*", "burn*", "burned",
    "साप चाव*", "सांप ने काट*", "snake bite", "snakebite", "bitten by a snake", "bitten",
    "heart attack", "हृदयविकार*", "छाती में दर्द", "chest pain", "chest pain*", "दिल का दर्द", "सांस नहीं", "saans nahi", "श्वास घेता येत नाही",
    "breathing difficulty", "can't breathe", "bleeding", "रक्तस्त्राव*", "खून बह*",
]
CRITICAL_MEDICATION_KEYWORDS = ["इन्सुलिन*", "इंसुलिन*", "insulin", "ऑक्सिजन*", "ऑक्सीजन*", "oxygen", "dialysis", "डायलिसिस*"]
MEDICAL_NEED_KEYWORDS = CRITICAL_MEDICATION_KEYWORDS + [
    "औषध*", "दवा", "दवाई*", "dawai", "dawa", "medicine*", "डॉक्टर*", "doctor*",
    "रुग्णवाहिका*", "एम्बुलेंस*", "एंबुलेंस*", "ambulance*",
    "bimar*", "bimaar", "sick", "unwell", "dawai chahiye", "dawai", "dawa chahiye",
]

NEED_KEYWORDS: dict[str, list[str]] = {
    "rescue_evacuation": ["बोट*", "boat*", "नाव", "नावेत", "बाहेर काढ*", "बाहर निकाल*", "nikalo", "nikaalo",
                          "rescue*", "evacuat*", "helicopter*", "हेलिकॉप्टर*", "ndrf", "बचा*", "वाचवा", "bachao", "bachaao"],
    "medical": MEDICAL_NEED_KEYWORDS,  # only explicit requests; emergencies are tracked separately
    "food": ["अन्न", "जेवण*", "खाना", "खाने", "khana", "khaana", "food", "ration*", "रेशन*", "hungry",
             # not "भूक*"/"bhook*": those prefixes also match भूकंप / bhookamp (earthquake)
             "भूक", "भुके*", "भूके*", "भूख", "भूखे", "भूखा", "bhooke", "bhookh*", "bhooka", "bhukhe", "bhookhe"],
    "drinking_water": ["पिण्याचे पाणी", "पिण्यासाठी पाणी", "पीने का पानी", "पीने के पानी", "peene ka paani",
                       "pine ka pani", "drinking water"],
    "shelter": ["need shelter", "shelter chahiye", "निवारा*", "आसरा चाहिए", "rehne ki jagah", "राहण्याची सोय"],
    "fire_services": ["अग्निशमन*", "फायर ब्रिगेड*", "fire brigade", "fire engine", "दमकल*", "fire tender"],
}

URGENCY_KEYWORDS: dict[str, list[str]] = {
    "critical": ["जीव धोक्यात", "जान खतरे*", "jaan khatre*", "मर जाएंगे", "मरून जाऊ", "mar jayenge", "डूब रहे",
                 "बुडत आहोत", "drowning", "dying", "तात्काळ", "तत्काल", "turant", "immediately", "sos",
                 "एसओएस", "इमर्जेंसी*", "इमरजेंसी*", "emergency"],
    "high": ["लवकर", "जल्दी", "jaldi", "lavkar", "urgent*", "quickly", "asap", "please help", "help fast",
             "मदत करा", "मदत पाठवा", "बचाओ", "बचाइए", "वाचवा", "bachao", "bachaao",
             "हेल्प*", "help me", "help us", "हेल्प मी*", "हेल्प अस*", "प्लीज़ हेल्प*", "please help me"],
    "low": ["सुरक्षित*", "safe", "ठीक है", "ठीक आहे", "theek hai", "thik hai", "no hurry", "not urgent",
            "घाई नाही", "jaldi nahi"],
    "medium": ["गरज आहे", "हवे आहे", "हवं आहे", "हवा आहे", "चाहिए", "chahiye", "need", "needed", "required", "पाहिजे"],
}
STATUS_KEYWORDS: dict[str, list[str]] = {
    "reported_safe": ["सुरक्षित*", "safe", "ठीक है", "ठीक आहे", "theek hai", "thik hai"],
    "reported_evacuated": ["निकल गय*", "nikal gay*", "evacuated", "बाहेर पडलो", "सुरक्षित ठिकाणी",
                          "बाहेर काढले", "बाहेर काढल*", "बाहर निकाल दिया", "rescue complete", "all rescued",
                          "कोणी अडकलेले नाही", "सगळ्यांना काढले"],
}

VULNERABLE_KEYWORDS: dict[str, list[str]] = {
    "elderly": ["वृद्ध*", "म्हातार*", "ज्येष्ठ*", "आजी*", "आजोबा*", "बुजुर्ग*", "बूढ*", "बुढ*", "दादी*", "नानी*",
                "buzurg*", "budhe", "budhi", "buddhe", "elderly", "senior*", "old man", "old woman", "old lady", "old people",
                "grandmother", "dadi", "nani", "aaji", "आजी", "दादी", "नानी",
                "aaji", "ajoba"],
    "children": ["मुले", "मुलं", "मुलां*", "मुलगा", "मुलगी", "विद्यार्थी*", "बच्चे", "बच्चों*", "बच्चा", "बच्ची",
                 "बालक*", "छात्र*", "bacche", "bachche", "bachhe", "baccha", "bachcha", "children", "child", "kids",
                 "kid", "boy", "girl", "students", "mule",
                "bachcha*", "bacha*", "bachche", "kid", "kids", "child", "children"],
    "infants": ["बाळ", "बाळाला", "बाळाचे", "बाळं", "तान्ह*", "नवजात*", "शिशु*", "baby", "babies", "infant*", "newborn*"],
    "pregnant_people": ["गरोदर*", "गर्भवती*", "प्रेग्नेंट*", "pregnant*", "garbhvati", "garbhwati", "प्रसूती*", "प्रसव*",
                        "delivery case", "labour pain*", "labor pain*"],
    "people_with_disabilities": ["अपंग*", "दिव्यांग*", "विकलांग*", "व्हीलचेअर*", "wheelchair*", "viklang", "disabled",
                                 "handicapped", "bedridden", "bed ridden", "अंथरुणाला खिळल*", "बिस्तर से उठ नहीं",
                                 "हलवता येत नाही", "chal nahi sakte", "चल नहीं सकते", "can't walk", "cannot walk"],
}

PEOPLE_NOUNS = ["लोक*", "जण*", "लोग*", "व्यक्ती*", "व्यक्ति*", "प्रवासी*", "यात्री*", "people", "persons", "person",
                "passengers", "log", "logon", "logo", "lok", "jan", "jann"]
FAMILY_NOUNS = ["कुटुंब*", "परिवार*", "families", "family", "parivar", "kutumb"]
APPROXIMATORS = {"सुमारे", "जवळपास", "अंदाजे", "साधारण", "लगभग", "करीब", "तकरीबन", "lagbhag", "kareeb", "karib",
                 "takriban", "around", "about", "approx", "approximately", "roughly", "nearly", "असतील", "होंगे",
                 "honge", "maybe", "jawalpas",
                 "से ज्यादा", "से ज़्यादा", "se zyada", "se jyada", "more than", "above", "over", "at least",
                 "पेक्षा जास्त", "पेक्षा अधिक"}
VAGUE_QUANTIFIERS = {"बरेच", "खूप", "अनेक", "बहुत", "कई", "कुछ", "सारे", "सब", "सगळे", "many", "several", "some",
                     "lots", "bahut", "kai", "kuch", "sab", "saare"}
RANGE_CONNECTORS = {"ते", "से", "to", "ya", "किंवा", "या"}

NUMBER_WORDS: dict[str, int] = {
    # Marathi
    "एक": 1, "दोन": 2, "तीन": 3, "चार": 4, "पाच": 5, "सहा": 6, "सात": 7, "आठ": 8, "नऊ": 9, "दहा": 10,
    "अकरा": 11, "बारा": 12, "पंधरा": 15, "वीस": 20, "पंचवीस": 25, "तीस": 30, "पस्तीस": 35, "चाळीस": 40,
    "पन्नास": 50, "साठ": 60, "सत्तर": 70, "ऐंशी": 80, "शंभर": 100, "एका": 1,
    # Hindi
    "दो": 2, "पांच": 5, "छह": 6, "छः": 6, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12, "पंद्रह": 15, "बीस": 20,
    "पच्चीस": 25, "पैंतीस": 35, "चालीस": 40, "पचास": 50, "अस्सी": 80, "सौ": 100,
    # romanised
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
    "aath": 8, "nau": 9, "das": 10, "gyarah": 11, "barah": 12, "pandrah": 15, "bees": 20, "pachees": 25,
    "pachchis": 25, "tees": 30, "chalis": 40, "chaalis": 40, "pachas": 50, "pachaas": 50, "sau": 100,
    # English
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "hundred": 100,
}
AGE_UNITS = {"साल", "वर्षे", "वर्षांचे", "वर्षांची", "वर्षाचा", "वर्षाची", "वर्ष", "saal", "sal", "years", "year", "yrs"}

LANG_MARKERS_MR = {"आहे", "आहेत", "आहोत", "आम्ही", "आमच्या", "आमचे", "आमचा", "इथे", "लवकर", "पाठवा", "करा", "झाले",
                   "झाली", "नाही", "मध्ये", "गावात", "आणि", "पण", "होते", "सगळे", "माझे", "माझ्या", "त्यांना", "संपला",
                   "आले", "या"}
LANG_MARKERS_HI = {"है", "हैं", "हम", "हमारे", "यहां", "जल्दी", "करो", "कीजिए", "भेजिए", "भेजो", "गया", "गई", "नहीं",
                   "में", "और", "के", "की", "का", "को", "से", "हुए", "रहा", "रही", "आइए", "हूं"}
LANG_MARKERS_HINGLISH = {"hai", "hain", "hum", "main", "mein", "se", "ka", "ki", "ke", "ko", "nahi", "paani", "pani",
                         "madad", "log", "bachao", "jaldi", "chahiye", "gaon", "ghar", "aao", "bhejo", "raha", "rahi",
                         "gaya", "gayi", "ab", "sab", "abhi", "paas", "karo", "pe", "par", "bhi", "aur"}
LANG_MARKERS_EN = {"the", "is", "are", "we", "there", "near", "people", "with", "and", "our", "of", "in", "a",
                   "need", "was", "has", "have", "including", "about", "but", "on", "at"}

VILLAGE_WORDS = {"गाव", "गावात", "गावामध्ये", "गावाजवळ", "गावातील", "गांव", "गांवमें", "gaon", "gaaon", "gav", "village"}
NOT_A_PLACE = {"कोणते", "कोणत्या", "कौन", "कौनसे", "हमारे", "हमारा", "आमच्या", "आमचे", "आमचं", "माझ्या", "मेरे", "मेरा",
               "which", "our", "my", "the", "a", "this", "that", "उस", "इस", "त्या", "या", "ek", "hamare", "mere",
               "hamara", "apne", "अपने", "pura", "पूरे", "सगळ्या", "same"}

QUALITY_MARKER_RE = r"\[(?:inaudible|noise|unclear|crosstalk|अस्पष्ट|शोर|आवाज)[^\]]*\]"
