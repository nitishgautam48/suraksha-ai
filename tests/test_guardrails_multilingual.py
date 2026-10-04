"""The advice guardrail must hold in every supported language, without blocking scam checks."""

import pytest

from backend.ai.guardrails import is_advice_request, output_violates_policy, refusal, sanitize_llm_output

# (language, stock-pick / buy-sell question, price-prediction question)
ADVICE = [
    ("en", "Which share should I buy this week?", "Will Bitcoin price go up next month?"),
    ("hinglish", "konsa share kharidna chahiye?", "Nifty kal upar jayega?"),
    ("hi", "मुझे कौन सा म्यूचुअल फंड खरीदना चाहिए?", "क्या सेंसेक्स कल गिरेगा?"),
    ("mr", "कोणता शेअर खरेदी करावा?", "उद्या निफ्टी वाढेल का?"),
    ("gu", "કયો શેર ખરીદું?", "કાલે સેન્સેક્સ વધશે?"),
    ("ta", "எந்த பங்கை வாங்க வேண்டும்?", "நாளை நிஃப்டி உயருமா?"),
    ("bn", "কোন শেয়ার কিনব?", "কাল কি সেনসেক্স বাড়বে?"),
    ("te", "ఏ షేర్ కొనాలి?", "రేపు నిఫ్టీ పెరుగుతుందా?"),
    ("kn", "ಯಾವ ಷೇರು ಖರೀದಿಸಬೇಕು?", "ನಾಳೆ ಸೆನ್ಸೆಕ್ಸ್ ಏರುತ್ತದೆಯೇ?"),
    ("ml", "ഏത് ഓഹരി വാങ്ങണം?", "നാളെ നിഫ്റ്റി ഉയരുമോ?"),
    ("pa", "ਕਿਹੜਾ ਸ਼ੇਅਰ ਖਰੀਦਣਾ ਚਾਹੀਦਾ ਹੈ?", "ਕੀ ਕੱਲ੍ਹ ਨਿਫਟੀ ਵਧੇਗਾ?"),
    ("or", "କେଉଁ ସେୟାର କିଣିବା ଉଚିତ?", "କାଲି ନିଫ୍ଟି ବଢ଼ିବ କି?"),
    ("as", "কোনটো শ্বেয়াৰ কিনিব লাগে?", "কাইলৈ চেনচেক্স বাঢ়িব নেকি? নিফটি"),
]

# (language, scam-check question, education question) - must NOT be refused.
SAFE = [
    ("en", "Someone on Telegram says this stock will double tomorrow. Is it a scam?", "What is a mutual fund?"),
    ("hinglish", "WhatsApp group bola share kal double hoga, kya ye fraud hai?", "SIP kya hota hai?"),
    ("hi", "व्हाट्सएप पर कहा कि शेयर दोगुना होगा, क्या यह धोखा है?", "म्यूचुअल फंड क्या होता है?"),
    ("mr", "हा शेअर दुप्पट होईल असा दावा केला आहे, ही फसवणूक आहे का?", "एसआयपी म्हणजे काय?"),
    ("gu", "આ શેર બમણો થશે એવો દાવો છે, શું આ છેતરપિંડી છે?", "મ્યુચ્યુઅલ ફંડ શું છે?"),
    ("ta", "இந்த பங்கு நாளை இரட்டிப்பாகும் என்கிறார்கள், இது மோசடியா?", "மியூச்சுவல் ஃபண்ட் என்றால் என்ன?"),
    ("bn", "বলছে এই শেয়ার কাল দ্বিগুণ হবে, এটা কি প্রতারণা?", "মিউচুয়াল ফান্ড কী?"),
    ("te", "ఈ షేర్ రేపు రెట్టింపు అవుతుందని చెబుతున్నారు, ఇది మోసమా?", "మ్యూచువల్ ఫండ్ అంటే ఏమిటి?"),
    ("kn", "ಈ ಷೇರು ನಾಳೆ ದುಪ್ಪಟ್ಟಾಗುತ್ತದೆ ಎಂದು ಹೇಳುತ್ತಿದ್ದಾರೆ, ಇದು ವಂಚನೆಯೇ?", "ಮ್ಯೂಚುವಲ್ ಫಂಡ್ ಎಂದರೇನು?"),
    ("ml", "ഈ ഓഹരി നാളെ ഇരട്ടിയാകുമെന്ന് പറയുന്നു, ഇത് തട്ടിപ്പാണോ?", "മ്യൂച്വൽ ഫണ്ട് എന്താണ്?"),
    ("pa", "ਕਹਿੰਦੇ ਹਨ ਇਹ ਸ਼ੇਅਰ ਕੱਲ੍ਹ ਦੁੱਗਣਾ ਹੋਵੇਗਾ, ਕੀ ਇਹ ਧੋਖਾ ਹੈ?", "ਮਿਊਚੁਅਲ ਫੰਡ ਕੀ ਹੈ?"),
    ("or", "ଏହି ସେୟାର କାଲି ଦୁଇଗୁଣ ହେବ ବୋଲି ଦାବି କରୁଛନ୍ତି, ଏହା ପ୍ରତାରଣା କି?", "ମ୍ୟୁଚୁଆଲ ଫଣ୍ଡ କ'ଣ?"),
    ("as", "এই শ্বেয়াৰ কাইলৈ দুগুণ হ'ব বুলি দাবী কৰিছে, এইটো প্ৰতাৰণা নেকি?", "মিউচুৱেল ফাণ্ড কি?"),
]

GENERAL_SAFE = [
    "How big should my emergency fund be?",
    "मेरा इमरजेंसी फंड कितना होना चाहिए?",
    "How do I report a UPI fraud to 1930?",
    "किसी ने OTP मांगा, क्या करूं?",
    "How do I check if an adviser is SEBI registered before investing?",
]


@pytest.mark.parametrize(("lang", "pick", "predict"), ADVICE, ids=[a[0] for a in ADVICE])
def test_advice_and_predictions_blocked_in_every_language(lang, pick, predict):
    assert is_advice_request(pick), f"{lang}: stock pick not blocked"
    assert is_advice_request(predict), f"{lang}: price prediction not blocked"


@pytest.mark.parametrize(("lang", "scam_check", "education"), SAFE, ids=[s[0] for s in SAFE])
def test_scam_checks_and_education_allowed_in_every_language(lang, scam_check, education):
    assert not is_advice_request(scam_check), f"{lang}: scam check wrongly refused"
    assert not is_advice_request(education), f"{lang}: education question wrongly refused"


@pytest.mark.parametrize("q", GENERAL_SAFE)
def test_general_safety_questions_allowed(q):
    assert not is_advice_request(q)


ADVICE_OUTPUT = [
    "आपको यह शेयर अभी खरीदना चाहिए।",
    "இந்த பங்கை வாங்க வேண்டும், இது சிறந்த தேர்வு.",
    "কাল এই শেয়ারের দাম বাড়বে।",
    "ఈ షేర్ కొనాలి, ఇది ఉత్తమ ఎంపిక.",
    "Nifty will reach 30000 next week.",
]
SAFE_OUTPUT = [
    "शेयर खरीदने से पहले सेबी पंजीकरण की जांच करें।",
    "व्हाट्सएप टिप्स पर कभी शेयर न खरीदें।",
    "ठग कहते हैं कि शेयर कल दोगुना हो जाएगा, यह झूठ है।",
    "பங்கு வாங்குவதற்கு முன் செபி பதிவை சரிபார்க்கவும்.",
    "Pump-and-dump scammers push a price up and then sell to new buyers.",
    "Never share your OTP. Call 1930 if you lose money.",
]


@pytest.mark.parametrize("text", ADVICE_OUTPUT)
def test_advice_in_model_output_detected(text):
    assert output_violates_policy(text)


@pytest.mark.parametrize("text", SAFE_OUTPUT)
def test_safety_guidance_in_model_output_kept(text):
    assert not output_violates_policy(text)


def test_sanitize_removes_only_the_advice_sentence():
    good = "यह संदेश एक घोटाला लगता है क्योंकि यह गारंटीड रिटर्न का वादा करता है और जल्दी पैसे भेजने को कहता है।"
    text, blocked = sanitize_llm_output(good + " आपको यह शेयर अभी खरीदना चाहिए।", "hi")
    assert blocked and text.startswith(good) and text.endswith(refusal("hi"))
    assert "खरीदना चाहिए" not in text


def test_shipped_strings_never_trip_the_output_filter():
    from backend import i18n

    for code in i18n.LANGUAGES:
        for key in ("refusal", "chat_fallback", "verdict_critical", "verdict_high", "action_critical"):
            assert not output_violates_policy(i18n.t(key, code)), f"{code}:{key}"
