"""Multilingual word lists for the investment-advice guardrail (all 12 supported languages).

Matching rules (see ``guardrails._matches``):
* ASCII entries match on word boundaries; a trailing ``*`` makes the entry a prefix (``share*``).
* Non-ASCII entries of one or two code points must equal a whole token; longer ones match as a
  substring, which handles Indian-language suffixes (``ಖರೀದಿಸಬೇಕು`` contains ``ಖರೀದಿ``).
* Text and entries are NFC-normalised with nukta signs and zero-width joiners removed, so
  ``ख़रीद`` / ``खरीद`` and ``బిట్‌కాయిన్`` / ``బిట్కాయిన్`` compare equal.

The lists are deliberately conservative and need review by native speakers. Each language uses
the script noted in the comment; Marathi shares Devanagari with Hindi and Assamese shares the
Bengali script.
"""

from __future__ import annotations

# Investment products / instruments (the *thing* a user may ask to buy or sell).
OBJECTS: tuple[str, ...] = (
    # English / Hinglish
    "share*", "stock*", "equity", "equities", "mutual fund*", "fund", "funds", "sip", "sips", "ipo*",
    "crypto*", "bitcoin*", "coin", "coins", "nifty", "sensex", "bank nifty", "f&o", "options",
    "futures", "etf*", "penny stock*", "multibagger*", "portfolio", "gold", "sona", "fd", "fds",
    "fixed deposit*", "bond", "bonds", "nps", "ppf", "scheme*", "smallcase*",
    # Hindi + Marathi (Devanagari)
    "शेयर", "शेअर", "स्टॉक", "म्यूचुअल फंड", "म्युच्युअल फंड", "फंड", "आईपीओ", "क्रिप्टो",
    "बिटकॉइन", "निफ्टी", "सेंसेक्स", "समभाग", "सोना", "सोने", "गोल्ड", "एफडी", "योजना",
    # Gujarati
    "શેર", "સ્ટોક", "મ્યુચ્યુઅલ ફંડ", "ફંડ", "આઈપીઓ", "ક્રિપ્ટો", "બિટકોઈન", "નિફ્ટી", "સેન્સેક્સ", "સોનું",
    # Tamil ("பங்க" is the stem of பங்கு / பங்கை / பங்குகள்)
    "பங்க", "ஷேர்", "ஸ்டாக்", "மியூச்சுவல் ஃபண்ட்", "ஃபண்ட்", "ஐபிஓ", "கிரிப்டோ", "பிட்காயின்",
    "நிஃப்டி", "சென்செக்ஸ்", "தங்கம்",
    # Bengali + Assamese (Bengali script)
    "শেয়ার", "শ্বেয়াৰ", "স্টক", "ষ্টক", "মিউচুয়াল ফান্ড", "ফান্ড", "আইপিও", "ক্রিপ্টো", "বিটকয়েন",
    "নিফটি", "সেনসেক্স", "সোনা",
    # Telugu
    "షేర్", "స్టాక్", "మ్యూచువల్ ఫండ్", "ఫండ్", "ఐపీఓ", "క్రిప్టో", "బిట్‌కాయిన్", "నిఫ్టీ", "సెన్సెక్స్", "బంగారం",
    # Kannada
    "ಷೇರು", "ಸ್ಟಾಕ್", "ಮ್ಯೂಚುವಲ್ ಫಂಡ್", "ಫಂಡ್", "ಐಪಿಒ", "ಕ್ರಿಪ್ಟೋ", "ಬಿಟ್‌ಕಾಯಿನ್", "ನಿಫ್ಟಿ", "ಸೆನ್ಸೆಕ್ಸ್", "ಚಿನ್ನ",
    # Malayalam
    "ഓഹരി", "ഷെയർ", "സ്റ്റോക്ക്", "മ്യൂച്വൽ ഫണ്ട്", "ഫണ്ട്", "ഐപിഒ", "ക്രിപ്റ്റോ", "ബിറ്റ്കോയിൻ",
    "നിഫ്റ്റി", "സെൻസെക്സ്", "സ്വർണ",
    # Punjabi (Gurmukhi)
    "ਸ਼ੇਅਰ", "ਸਟਾਕ", "ਮਿਊਚੁਅਲ ਫੰਡ", "ਫੰਡ", "ਆਈਪੀਓ", "ਕ੍ਰਿਪਟੋ", "ਬਿਟਕੋਇਨ", "ਨਿਫਟੀ", "ਸੈਂਸੈਕਸ", "ਸੋਨਾ",
    # Odia
    "ସେୟାର", "ଷ୍ଟକ", "ମ୍ୟୁଚୁଆଲ ଫଣ୍ଡ", "ଫଣ୍ଡ", "ଆଇପିଓ", "କ୍ରିପ୍ଟୋ", "ବିଟକଏନ", "ନିଫ୍ଟି", "ସେନସେକ୍ସ", "ସୁନା",
)  # fmt: skip

# Phrases removed before matching so that savings vocabulary is never mistaken for a product.
SAFE_PHRASES: tuple[str, ...] = (
    "emergency fund", "emergency funds", "इमरजेंसी फंड", "आपातकालीन फंड", "आपातकालीन निधि",
    "आपत्कालीन निधी", "ઇમરજન્સી ફંડ", "அவசர நிதி", "জরুরি তহবিল", "అత్యవసర నిధి", "ತುರ್ತು ನಿಧಿ",
    "അടിയന്തര ഫണ്ട്", "ਐਮਰਜੈਂਸੀ ਫੰਡ", "ଜରୁରୀକାଳୀନ ପାଣ୍ଠି",
)  # fmt: skip

# Price / market words (for prediction questions).
PRICE: tuple[str, ...] = (
    "price*", "rate", "rates", "valuation", "market", "markets", "bhav", "bhaav", "daam", "keemat", "kimat",
    "भाव", "कीमत", "दाम", "रेट", "किंमत", "बाजार", "मार्केट",
    "ભાવ", "કિંમત", "બજાર",
    "விலை", "சந்தை",
    "দাম", "মূল্য", "বাজার", "বজাৰ",
    "ధర", "మార్కెట్",
    "ಬೆಲೆ", "ದರ", "ಮಾರುಕಟ್ಟೆ",
    "വില", "വിപണി",
    "ਕੀਮਤ", "ਭਾਅ", "ਰੇਟ", "ਬਾਜ਼ਾਰ", "ਮਾਰਕੀਟ",
    "ଦାମ", "ମୂଲ୍ୟ", "ଦର", "ବଜାର",
)  # fmt: skip

# Buy / sell / hold / invest verbs.
ACTIONS: tuple[str, ...] = (
    "buy*", "sell*", "hold", "holding", "invest*", "exit", "book profit", "average out",
    "kharid*", "khareed*", "bech*", "nivesh*", "paisa laga*", "paise laga*",
    # Hindi
    "खरीद", "बेच", "निवेश", "होल्ड", "पैसा लगा", "पैसे लगा",
    # Marathi
    "खरेदी", "विकत घ्या", "विकू", "विकाव", "विकाय", "गुंतवणूक", "गुंतव",
    # Gujarati
    "ખરીદ", "વેચ", "રોકાણ",
    # Tamil ("வாங்க" alone also means "come", so only buy-forms are listed)
    "வாங்கல", "வாங்குவ", "வாங்கவ", "வாங்கணும்", "வாங்க வேண்டும்", "வாங்கிட", "வாங்குங்கள்",
    "விற்க", "விற்பனை", "விற்கல", "முதலீடு", "முதலீட்",
    # Bengali ("কিন্তু" = "but" is avoided by listing full forms)
    "কিনব", "কিনি", "কিনে", "কিনতে", "কিনুন", "কেনা", "বিক্রি", "বেচব", "বেচে", "বিনিয়োগ",
    # Assamese
    "কিনিব", "কিনো", "কিনা", "বিক্ৰী", "বেচিব",
    # Telugu ("అమ్మ" alone means "mother")
    "కొనాల", "కొనవచ్చ", "కొనండి", "కొనుగోలు", "కొంటే", "కొనమ", "అమ్మాల", "అమ్మేయ", "అమ్మకం",
    "అమ్మవచ్చ", "పెట్టుబడి",
    # Kannada
    "ಖರೀದಿ", "ಕೊಳ್ಳ", "ಮಾರಾಟ", "ಮಾರಬೇಕ", "ಮಾರಲ", "ಹೂಡಿಕೆ", "ಹೂಡ",
    # Malayalam
    "വാങ്ങ", "വിൽക്ക", "വിൽപ്പന", "നിക്ഷേപ",
    # Punjabi
    "ਖਰੀਦ", "ਵੇਚ", "ਨਿਵੇਸ਼",
    # Odia
    "କିଣ", "ବିକ୍ରି", "ବିକିବ", "ନିବେଶ",
)  # fmt: skip

# "Which / should / good / advise" - turns buy/sell + product into a request for a recommendation.
ADVICE_MARKERS: tuple[str, ...] = (
    "should*", "which", "best", "top", "recommend*", "suggest*", "advice", "advise*", "tip", "tips",
    "worth", "good time", "right time",
    "kaunsa", "konsa", "kon sa", "kaun sa", "kaunse", "konse", "accha", "achha", "acha", "chahiye",
    "chaiye", "salah", "sujhav", "batao", "bataiye", "sahi samay",
    "कौन सा", "कौनसा", "कौन से", "कौन-सा", "सबसे अच्छा", "सबसे अच्छे", "बेहतर", "चाहिए", "सलाह",
    "टिप", "सुझाव", "बताओ", "बताइए", "बताएं", "सही समय",
    "कोणता", "कोणते", "कोणती", "सर्वोत्तम", "चांगला", "चांगले", "घ्यावा", "घ्यावे", "करावी", "पाहिजे", "सल्ला",
    "કયો", "કયા", "કઈ", "કયું", "શ્રેષ્ઠ", "સારો", "સારા", "જોઈએ", "સલાહ",
    "எந்த", "சிறந்த", "வேண்டுமா", "வேண்டும்", "பரிந்துரை", "நல்ல", "லாமா", "ஆலோசனை",
    "কোন", "কোনটা", "সেরা", "ভালো", "উচিত", "পরামর্শ",
    "কোনটো", "শ্ৰেষ্ঠ", "ভাল", "পৰামৰ্শ",
    "ఏ", "ఏది", "ఉత్తమ", "మంచి", "సలహా",
    "ಯಾವ", "ಉತ್ತಮ", "ಒಳ್ಳೆಯ", "ಬೇಕು", "ಬೇಕಾ", "ಸಲಹೆ",
    "ഏത്", "ഏതു", "മികച്ച", "നല്ല", "വേണോ", "വേണം", "ഉപദേശ",
    "ਕਿਹੜਾ", "ਕਿਹੜੇ", "ਕਿਹੜੀ", "ਵਧੀਆ", "ਬਿਹਤਰ", "ਚਾਹੀਦਾ", "ਚਾਹੀਦੀ", "ਸਲਾਹ",
    "କେଉଁ", "ସର୍ବୋତ୍ତମ", "ଭଲ", "ଉଚିତ", "ପରାମର୍ଶ", "ଦରକାର",
)  # fmt: skip

# Superlatives that make "<superlative> <product>" a product recommendation on their own.
BEST: tuple[str, ...] = (
    "best", "top", "multibagger*", "sabse accha", "sabse achha",
    "सबसे अच्छा", "सबसे अच्छे", "सबसे बढ़िया", "टॉप", "सर्वोत्तम", "सगळ्यात चांगला",
    "શ્રેષ્ઠ", "સૌથી સારો", "சிறந்த", "সেরা", "শ্ৰেষ্ঠ", "ఉత్తమ", "ಉತ್ತಮ", "മികച്ച", "ഏറ്റവും നല്ല",
    "ਸਭ ਤੋਂ ਵਧੀਆ", "ସର୍ବୋତ୍ତମ", "ସବୁଠୁ ଭଲ",
)  # fmt: skip

# Up / down / target words (for price-prediction questions).
MOVES: tuple[str, ...] = (
    "go up", "going up", "goes up", "rise", "rising", "fall", "falling", "crash*", "increase", "decrease",
    "reach", "double", "triple", "target", "moon", "up or down", "bullish", "bearish", "rally", "breakout",
    "upar", "neeche", "niche", "badhega", "badhegi", "badhenge", "badhna", "girega", "giregi", "girenge",
    "chadhega", "chadhegi", "tootega", "tutega",
    "ऊपर", "नीचे", "बढ़ेग", "बढ़ेंग", "बढ़ने", "गिरेग", "गिरेंग", "गिरने", "चढ़ेग", "टूटेग", "टारगेट", "दोगुन", "लक्ष्य",
    "वाढेल", "वाढ", "घसरेल", "घसर", "पडेल", "वर जाईल", "खाली येईल",
    "વધશે", "વધ", "ઘટશે", "ઘટ", "ઉપર", "નીચે", "તૂટશે",
    "உயரும்", "உயர", "ஏறும்", "ஏறுமா", "இறங்கும்", "சரியும்", "விழும்", "குறையும்",
    "বাড়বে", "বাড়", "কমবে", "উঠবে", "নামবে", "পড়বে",
    "বাঢ়িব", "বাঢ়", "কমিব", "উঠিব", "নামিব",
    "పెరుగు", "తగ్గు", "పడిపో",
    "ಏರುತ್ತ", "ಏರಿಕೆ", "ಹೆಚ್ಚಾಗ", "ಇಳಿಯುತ್ತ", "ಇಳಿಕೆ", "ಕುಸಿ",
    "ഉയരു", "ഉയര", "കയറു", "ഇടിയു", "താഴു", "കുറയു",
    "ਵਧੇਗਾ", "ਵਧੇਗੀ", "ਵਧ", "ਘਟੇਗਾ", "ਘਟ", "ਡਿੱਗ", "ਉੱਪਰ", "ਹੇਠਾਂ",
    "ବଢ଼ିବ", "ବଢ଼", "କମିବ", "ଖସିବ", "ଉପରକୁ", "ତଳକୁ",
)  # fmt: skip

# Time words that make a movement question about the future.
TIME_WORDS: tuple[str, ...] = (
    "tomorrow", "today", "next week", "next month", "next year", "this week", "this month", "this year",
    "kal", "aaj", "agle hafte", "agle mahine", "is hafte", "is saal",
    "कल", "आज", "अगले", "इस हफ्ते", "इस साल", "उद्या", "पुढच्या",
    "કાલે", "આવતીકાલે", "આવતા", "நாளை", "அடுத்த", "কাল", "আগামী", "কাইলৈ", "অহা",
    "రేపు", "వచ్చే", "ನಾಳೆ", "ಮುಂದಿನ", "നാളെ", "അടുത്ത", "ਕੱਲ੍ਹ", "ਅਗਲੇ", "କାଲି", "ଆସନ୍ତା",
)  # fmt: skip

PREDICT_MARKERS: tuple[str, ...] = (
    "predict*", "forecast*", "will", "expect*", "going to", "likely", "chance*",
    "jayega", "jaega", "jaayega", "jayegi", "hoga", "hogi", "lagta",
    "जाएगा", "जायेगा", "जाएगी", "होगा", "होगी", "लगता", "संभावना", "अनुमान", "भविष्यवाणी",
)  # fmt: skip

# Scam / claim / verification context: the user is checking a claim, not asking for a pick.
EXEMPT: tuple[str, ...] = (
    "scam*", "fraud*", "fake", "cheat*", "genuine", "legit*", "report*", "complain*", "1930", "phishing",
    "ponzi", "pump and dump", "claim*", "promis*", "guarantee*", "they say", "says", "said", "told me",
    "verify", "verified", "registered", "sebi", "rbi", "research",
    "dhokha", "thagi", "farzi", "nakli", "asli", "bola", "keh raha", "kehta", "dawa",
    "धोखा", "धोखाधड़ी", "ठगी", "ठग", "फ्रॉड", "फर्जी", "नकली", "स्कैम", "शिकायत", "असली", "दावा", "वादा",
    "गारंटी", "कह रहा", "कहते", "कहता", "बोला", "जांच", "जाँच", "सत्याप", "पंजीकृत", "सेबी",
    "फसवणूक", "फसव", "बनावट", "खोटा", "तक्रार", "हमी", "तपास",
    "છેતરપિંડી", "છેતર", "ફ્રોડ", "નકલી", "બનાવટી", "ફરિયાદ", "દાવો", "ગેરંટી", "સેબી", "ચકાસ",
    "மோசடி", "ஏமாற்", "போலி", "புகார்", "உறுதி", "வாக்குறுதி", "சொல்கிறார்", "கூறுகிறார்", "செபி", "சரிபார்",
    "প্রতারণা", "প্রতারক", "জালিয়াতি", "ভুয়া", "স্ক্যাম", "অভিযোগ", "দাবি", "গ্যারান্টি", "বলছে", "সেবি", "যাচাই",
    "প্ৰতাৰণা", "প্ৰতাৰক", "ভুৱা", "দাবী", "পৰীক্ষা",
    "మోసం", "మోస", "నకిలీ", "స్కామ్", "ఫిర్యాదు", "హామీ", "గ్యారంటీ", "చెబుతున్నార", "సెబీ", "తనిఖీ",
    "ವಂಚನೆ", "ವಂಚಕ", "ಮೋಸ", "ನಕಲಿ", "ದೂರು", "ಭರವಸೆ", "ಗ್ಯಾರಂಟಿ", "ಹೇಳುತ್ತಿದ್ದಾರೆ", "ಸೆಬಿ", "ಪರಿಶೀಲ",
    "തട്ടിപ്പ", "വ്യാജ", "വഞ്ചന", "പരാതി", "ഉറപ്പ", "ഗ്യാരന്റി", "പറയുന്നു", "സെബി", "പരിശോധ",
    "ਧੋਖਾ", "ਠੱਗੀ", "ਠੱਗ", "ਨਕਲੀ", "ਫਰਜ਼ੀ", "ਸ਼ਿਕਾਇਤ", "ਦਾਅਵਾ", "ਗਾਰੰਟੀ", "ਸੇਬੀ", "ਜਾਂਚ",
    "ପ୍ରତାରଣା", "ଠକେଇ", "ଠକ", "ନକଲି", "ଅଭିଯୋଗ", "ଦାବି", "ଗ୍ୟାରେଣ୍ଟି", "ସେବି", "ଯାଞ୍ଚ",
)  # fmt: skip

# "How do I ..." / "what is ..." - process or concept questions, not requests for a pick.
HOW_TO: tuple[str, ...] = (
    "how", "what is", "what are", "meaning", "kaise", "kya hota", "kya hai", "matlab",
    "कैसे", "क्या होता", "क्या है", "मतलब", "कसे", "म्हणजे काय", "કેવી રીતે", "શું છે", "எப்படி", "என்றால் என்ன",
    "কিভাবে", "কী", "কেনেকৈ", "ఎలా", "అంటే ఏమిటి", "ಹೇಗೆ", "ಎಂದರೇನು", "എങ്ങനെ", "എന്താണ്", "ਕਿਵੇਂ", "ਕੀ ਹੈ",
    "କିପରି", "କ'ଣ",
)  # fmt: skip

# Negations: "do not buy ..." is safety guidance, not advice.
NEGATIONS: tuple[str, ...] = (
    "not", "never", "don't", "dont", "do not", "avoid", "no", "mat", "nahi", "nahin", "na",
    "मत", "न", "नहीं", "ना", "बचें", "नका", "नाही", "नये", "નહીં", "ન", "ના", "ટાળો",
    "வேண்டாம்", "கூடாது", "இல்லை", "தவிர்", "না", "নয়", "এড়িয়ে", "নকৰিব", "নহয়", "নাই",
    "వద్దు", "కాదు", "లేదు", "చేయకండి", "ಬೇಡ", "ಇಲ್ಲ", "ಮಾಡಬೇಡಿ", "അരുത്", "ഇല്ല", "വേണ്ട",
    "ਨਾ", "ਨਹੀਂ", "ਮਤ", "ନାହିଁ", "ନା", "କରନ୍ତୁ ନାହିଁ",
    # negative verb suffixes / forms (Dravidian languages and Assamese negate inside the verb)
    "ில்லை", "மாட்டேன்", "மாட்டோம்", "ില്ല", "ಿಲ್ಲ", "ದಿಲ್ಲ", "చేయను", "ఇవ్వను", "చేయము", "చెప్పను",
    "নিদিওঁ", "নকৰো", "নকৰে", "নেই", "નથી", "ନୁହେଁ",
)  # fmt: skip

# Recommendation wording in model output.
REC_MARKERS: tuple[str, ...] = (
    "should", "recommend*", "suggest*", "best", "good option", "good choice", "worth buying", "go for",
    "consider buying", "chahiye", "accha option",
    "चाहिए", "सलाह", "सुझाव", "बेहतर रहेगा", "अच्छा विकल्प", "सबसे अच्छा", "पाहिजे", "घ्यावा", "घ्यावे",
    "सर्वोत्तम", "चांगला पर्याय", "જોઈએ", "શ્રેષ્ઠ", "સારો વિકલ્પ", "வேண்டும்", "சிறந்த", "பரிந்துரை",
    "উচিত", "সেরা", "পরামর্শ", "শ্ৰেষ্ঠ", "পৰামৰ্শ", "ఉత్తమ", "మంచి ఎంపిక", "సిఫార్సు", "కొనండి", "కొనాలి",
    "ಉತ್ತಮ", "ಶಿಫಾರಸು", "ಬೇಕು", "മികച്ച", "ശുപാർശ", "വേണം", "ਚਾਹੀਦਾ", "ਵਧੀਆ", "ਸਿਫਾਰਸ਼", "ଉଚିତ",
    "ସର୍ବୋତ୍ତମ", "ସୁପାରିଶ",
)  # fmt: skip
