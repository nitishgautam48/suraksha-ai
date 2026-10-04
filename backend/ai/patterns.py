"""Rule-based manipulation / scam signal library.

Each detector is a set of regexes (English, Hinglish and Devanagari Hindi) mapped to a risk
category and weight. Rules give a deterministic, explainable baseline that works even when the
LLM is unavailable, and they produce character spans used for highlighting risky sections.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Detector:
    key: str
    category: str  # one of RISK_CATEGORIES
    label: str
    weight: int  # contribution to a 0..100 score
    reason: str
    patterns: tuple[str, ...]
    negatable: bool = False  # ignore matches preceded by "never / do not / don't"
    compiled: tuple[re.Pattern, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "compiled", tuple(re.compile(p, re.IGNORECASE | re.UNICODE) for p in self.patterns))


RISK_CATEGORIES = {
    "ponzi_scheme": "Ponzi Scheme",
    "guaranteed_returns": "Guaranteed Returns",
    "fake_advisor": "Fake Advisor",
    "pump_and_dump": "Pump and Dump",
    "impersonation": "Impersonation",
    "phishing": "Phishing",
    "urgency_manipulation": "Urgency Manipulation",
    "social_engineering": "Social Engineering",
}

# Social-media tactic labels (Module 3) and WhatsApp warning flags (Module 2) map onto detectors.
DETECTORS: tuple[Detector, ...] = (
    Detector(
        "guaranteed_returns",
        "guaranteed_returns",
        "Guaranteed returns",
        30,
        "Promises guaranteed or risk-free returns. No legitimate investment can guarantee returns.",
        (
            r"\bguarantee[ds]?\b.{0,40}\b(return|profit|income|payout|gain|interest)s?\b",
            r"\b(return|profit|income|interest|payout)s?\b.{0,30}\bguarantee[ds]?\b",
            r"\b(capital|principal|money)\s+(is\s+)?(safe|protected|secure)\b",
            r"\b(return|munafa|profit|interest)\s+(milega|pakka|fix)\b",
            r"\b(risk[- ]?free|zero[- ]?risk|no[- ]?risk|100\s*%\s*(safe|secure|sure|guaranteed))\b",
            r"\b(fixed|assured|sure[- ]?shot|pakka)\b.{0,25}\b(return|profit|income|munafa|kamai)",
            r"गारंटी(ड)?\s*(रिटर्न|मुनाफ़?ा|लाभ)",
            r"पक्का\s*(मुनाफ़?ा|रिटर्न)",
        ),
    ),
    Detector(
        "unrealistic_profits",
        "guaranteed_returns",
        "Unrealistic profits",
        25,
        "Mentions returns far above what regulated products typically offer.",
        (
            r"\b(double|triple|10x|5x|3x|2x)\b.{0,30}\b(money|investment|capital|paisa|amount|portfolio|savings)\b",
            r"\d+(\.\d+)?\s*%\s*(daily|weekly|monthly|per (day|week|month)|a (day|week|month)|every (day|week|month))",
            r"\b(har|every)\s+(din|hafte|mahine|day|week|month)\b.{0,25}\d+(\.\d+)?\s*%",
            r"\b(monthly|daily|weekly)\s+(roi|returns?|profit|interest)\b.{0,15}\d+\s*%",
            r"\blagao\b.{0,40}\b(pakka|double|milega|lakh)\b",
            r"\bturn\s+(rs\.?|₹)?\s*\d[\d,]*\s*(k|lakh)?\s+into\s+(rs\.?|₹)?\s*\d",
            r"\bearn\s+(rs\.?|₹)?\s*\d[\d,]*\s*(k|lakh)?\s+(weekly|daily|monthly|every (day|week|month))\b",
            r"\b(money|paisa|investment)\b.{0,20}\b(double|triple)\b",
            r"\b\d{2,4}\s*%\s*(return|profit|gain|monthly|per month|daily|weekly|a month|a week)",
            r"\b(daily|weekly|monthly)\s+(profit|return|income|payout)s?\s+of\s+\d",
            r"\bearn\s+(rs\.?|₹|inr)?\s*\d[\d,]*\s*(k|thousand|lakh|lakhs|crore)?\s*(per|a|every|daily|/)\s*(day|week|month)",
            r"(₹|rs\.?|inr)\s?\d[\d,]*\s*(k|lakh|lakhs|crore)?\s*(daily|per day|roz|har din)",
            r"\b(get rich quick|crorepati|financial freedom in \d+ (days|weeks|months))\b",
            r"पैसा\s*डबल|दोगुना",
        ),
    ),
    Detector(
        "ponzi_referral",
        "ponzi_scheme",
        "Referral / chain income",
        25,
        "Pays you for recruiting others or for 'levels' - a hallmark of Ponzi and pyramid schemes.",
        (
            r"\b(refer|referral|invite|join)\b.{0,40}\b(earn|bonus|commission|income|reward)\b",
            r"\b(level|binary|matrix|downline|upline|team)\s+(income|bonus|commission|plan)\b",
            r"\b(mlm|multi[- ]level|pyramid|chain system)\b",
            r"\b(jod(o|na|ne)|add kar(o|na|ke)|refer kar(o|na))\b.{0,40}\b(bonus|commission|income|kamai|paisa)\b",
            r"\b(log|logon|members?|relatives|friends|investors)\b.{0,20}\b(jod(o|na|ne)|add kar(o|na)|bring|recruit)\b",
            r"\b(bring|recruit|add)\s+\d+\s+(new\s+)?(investors?|members?|people|friends)\b",
            r"\bdeposit\b.{0,40}\b(withdraw|payout)\b.{0,40}\b(daily|weekly|instantly)\b",
        ),
    ),
    Detector(
        "fake_advisor",
        "fake_advisor",
        "Unregistered advisor / tips",
        25,
        "Offers tips or 'sure-shot' calls from an unverified advisor. SEBI-registered advisers never promise returns.",
        (
            r"\b(sure[- ]?shot|jackpot|operator|insider|inside)\s+(tip|call|info|news|stock|share)s?\b",
            r"\b(premium|vip|paid)\s+(group|channel|tips|calls|membership)\b",
            r"\b(stock|share|option|crypto|forex)\s+(tips?|calls?|signals?)\b",
            r"\b(sebi|rbi)[- ]?(registered|approved|certified)\b.{0,40}\b(guarantee|assured|profit)\b",
            r"\b(trading|investment)\s+(guru|expert|mentor|coach)\b.{0,40}\b(join|whatsapp|telegram|dm)\b",
            r"\b(100|9\d)\s*%\s*accura(te|cy)\b",
            r"\b(i|we)\s+(will|can)\s+(trade|invest|manage)\b.{0,30}\b(for you|on your behalf)\b",
            r"\b(institutional|vip|elite|premium)\s+(account|trading account|investors? club|club)\b",
            r"\b(stock|investment|trading)\s+(study|learning|discussion)\s+group\b",
            r"\b(ipo|ofs|block deal|block trade)s?\b.{0,40}\b(discount|special price|guaranteed allotment|allotment at)\b",
        ),
    ),
    Detector(
        "pump_language",
        "pump_and_dump",
        "Pump language",
        35,
        "Hype urging people to pile into a little-known stock or coin - a common pump-and-dump pattern.",
        (
            r"\b(to the moon|moon ?shot|rocket|multibagger|multi[- ]bagger|next (big|100x)|hidden gem)\b",
            r"\b(penny|small[- ]?cap|micro[- ]?cap)\s+(stock|share|coin)s?\b.{0,40}\b(buy|grab|load|accumulate)\b",
            r"\b(buy|load|grab|accumulate)\b.{0,20}\b(now|today|before)\b.{0,30}\b(rally|jump|explode|fly|skyrocket)",
            r"\b(upper circuit|operator (is )?buying|big news coming|target\s*(price)?\s*[:=]?\s*₹?\d)",
            r"🚀{2,}|📈{2,}|💰{2,}",
        ),
    ),
    Detector(
        "impersonation",
        "impersonation",
        "Fake authority",
        25,
        "Claims to be from a regulator, bank, government body or well-known company.",
        (
            r"\b(sebi|rbi|reserve bank|income tax|it department|npci|uidai|trai|cbi|enforcement directorate|police|cyber cell|customs)\b.{0,60}\b(notice|officer|department|verify|penalty|block|suspend|arrest|warrant|kyc)\b",
            r"\b(bank|sbi|hdfc|icici|axis|kotak|paytm|phonepe|gpay|google pay)\b.{0,40}\b(officer|executive|manager|team|support)\b.{0,40}\b(call|verify|update|share|kyc)\b",
            r"\b(this is my new number|my new number|lost my phone|phone (is )?(broken|lost))\b",
            r"\b(endorsed|backed|approved) by\b.{0,30}\b(government|modi|sebi|rbi|ambani|tata|celebrity)\b",
            r"\b(government|govt|sebi|rbi)[- ]?(approved|backed|certified)\b.{0,40}\b(invest|platform|scheme|earn)",
            r"\b(ambani|adani|tata|narayana murthy|nirmala sitharaman|elon musk|shah rukh|sachin tendulkar|rbi governor)\b.{0,60}\b(invest(ment)?|platform|scheme|earn|app)\b",
            r"\b(electricity|power|bijli|gas)\s+(department|board|office)\b.{0,80}\b(disconnect|cut|officer)",
            r"(आरबीआई|सेबी|पुलिस|सीबीआई).{0,40}(नोटिस|गिरफ्तार|ब्लॉक)",
        ),
    ),
    Detector(
        "digital_arrest",
        "impersonation",
        "'Digital arrest' / seized-parcel threat",
        60,
        "Fake police, CBI or customs officials threaten arrest over a parcel or ID misuse. There is no 'digital arrest' in Indian law.",
        (
            r"\b(digital(ly)? arrest(ed)?|under (digital )?arrest)\b",
            r"\bparcel\b.{0,60}\b(seized|held|drugs|narcotics|illegal items|contraband)\b",
            r"\b(drugs|narcotics)\b.{0,30}\b(parcel|courier|package)\b",
            r"\b(money laundering|hawala)\b.{0,60}\b(aadhaar|account|case|arrest)\b",
            r"\b(video call|stay on (the )?(call|camera))\b.{0,60}\b(police|cbi|officer|arrest|investigation)\b",
            r"\b(do not|don'?t) (disconnect|cut) (this|the) (call|video call)\b",
        ),
    ),
    Detector(
        "credential_request",
        "phishing",
        "OTP / PIN / password request",
        55,
        "Asks you to share an OTP, UPI PIN, CVV or password. No bank, regulator or company ever asks for these.",
        (
            r"\b(share|send|tell|provide|enter|confirm|forward|give)\b.{0,30}\b(otp|pin|cvv|password|passcode|mpin|upi pin|card (number|details)|net ?banking|(demat|bank|net ?banking) login|login (id|details|credentials))\b",
            r"\b(with|using)\s+(your\s+)?(upi\s+)?pin\b",
            r"\b(card number|expiry)\b.{0,30}\b(cvv)\b",
            r"\b(share|tell)\b.{0,20}\b(code|access code)\b.{0,20}\b(receive|sent|you get)\b",
            r"\b(anydesk|teamviewer|quicksupport|rustdesk)\b.{0,40}\b(code|id|access)\b",
            r"\b(otp|cvv|upi pin|mpin)\b.{0,30}\b(share|send|bata(o|yein|en)?|dijiye)\b",
            r"\b(enter|use) (your )?upi pin\b.{0,30}\b(receive|get|claim|refund|credit)\b",
            r"ओटीपी\s*(बताएं|शेयर|भेजें)|पिन\s*(बताएं|शेयर)",
        ),
        negatable=True,
    ),
    Detector(
        "phishing",
        "phishing",
        "Phishing link / fake KYC",
        35,
        "Pushes a link, app download or 'KYC update' - common ways to steal banking details.",
        (
            r"\b(kyc|pan|aadhaar|account)\b.{0,30}\b(update|verify|expire[ds]?|suspend|block)",
            r"\b(click|tap|open|visit)\b.{0,25}\b(link|url|here|below)\b",
            r"\b(download|install)\b.{0,30}\b(app|apk|anydesk|teamviewer|quicksupport|screen ?share)\b",
            r"\.apk\b",
            r"\b(scan (this|the) qr|qr code)\b.{0,40}\b(receive|get|claim|refund)\b",
        ),
        negatable=True,
    ),
    Detector(
        "lottery_prize",
        "social_engineering",
        "Lottery / prize bait",
        40,
        "Claims you won a lottery, prize, cashback or lucky draw - genuine prizes never require an upfront payment.",
        (
            r"\b(congratulations|congrats|you (have )?won|you('ve| have)? been selected|winner)\b.{0,60}\b(lottery|prize|reward|cashback|lucky draw|jackpot|kbc|gift|car|iphone|lakh|crore)\b",
            r"\b(kbc|kaun banega crorepati|lucky draw|lottery)\b.{0,40}\b(won|winner|prize|claim)\b",
            r"\b(claim|redeem)\s+(your\s+)?(prize|reward|cashback|gift|lottery)\b",
            r"(लॉटरी|इनाम).{0,30}(जीत|जीता|विजेता)",
        ),
    ),
    Detector(
        "urgency",
        "urgency_manipulation",
        "Urgency / scarcity",
        20,
        "Creates artificial time pressure so you act before thinking.",
        (
            r"\b(act|join|invest|pay|respond|hurry)\b.{0,15}\b(now|immediately|fast|today|asap)\b",
            r"\b(only|just)\s+\d+\s+(slots?|seats?|spots?|hours?|minutes?|left|remaining)\b",
            r"\b(limited|last)\s+(time|offer|chance|slots?|seats?|few)\b",
            r"\b(offer|deal|window)\s+(ends|closes|expires)\b",
            r"\b(within|in)\s+\d+\s*(minutes?|mins?|hours?|hrs?)\b",
            r"\b(urgent(ly)?|immediately|right now|don'?t miss|ending soon|today only)\b",
            r"\b(jaldi|abhi|turant)\b",
            r"(जल्दी|तुरंत|अभी)\s*(करें|जुड़ें|निवेश)",
        ),
    ),
    Detector(
        "fomo",
        "urgency_manipulation",
        "FOMO tactics",
        15,
        "Plays on fear of missing out - 'everyone is earning, don't be left behind'.",
        (
            r"\b(don'?t|do not)\s+(miss|be left|regret)\b",
            r"\b(everyone|thousands|lakhs of people|people)\s+(is|are)\s+(earning|joining|making|investing)\b",
            r"\b(fomo|once[- ]in[- ]a[- ]lifetime|golden (chance|opportunity)|never again)\b",
            r"\b(you('| wi)ll regret|late(r)? (you will|you'll) cry)\b",
        ),
    ),
    Detector(
        "fear",
        "social_engineering",
        "Fear tactics",
        20,
        "Threatens penalties, arrest, account blocking or loss to scare you into compliance.",
        (
            r"\b(account|card|sim|pan|kyc|number)\b.{0,30}\b(will be|is|has been|getting)\s+(blocked|suspended|deactivated|frozen|closed|disconnected)\b",
            r"\b(avoid|prevent|stop)\b.{0,20}\b(suspension|deactivation|blocking|disconnection|penalty|legal action)\b",
            r"\b(legal action|arrest(ed)?|fir|penalty|fine|court|warrant|jail)\b",
            r"\b(last (warning|notice)|final (warning|notice|reminder))\b",
            r"\b(power|electricity|bijli|connection|gas|sim|number|service)\b.{0,40}\b(will be |be )?(disconnected|cut off|kat jayega|band ho jayega)\b",
            r"\b(will|shall)\s+(lapse|expire|be cancelled|be forfeited)\b",
            r"(ब्लॉक|बंद)\s*(हो जाएगा|कर दिया जाएगा)",
        ),
    ),
    Detector(
        "emotional",
        "social_engineering",
        "Emotional manipulation",
        15,
        "Uses emotions - pity, greed, love or family pressure - to bypass careful judgement.",
        (
            r"\b(trust me|believe me|i swear|god promise|bharosa (rakho|karo))\b",
            r"\b(your family|your children|your future)\b.{0,40}\b(deserve|secure|suffer|depend)\b",
            r"\b(life[- ]changing|change your life|dream (car|house|life)|quit your job)\b",
            r"\b(secret|they don'?t want you to know|banks hate|hidden method)\b",
            r"\b(help me|emergency|stuck at|hospital)\b.{0,40}\b(send|transfer|pay|bhej)",
        ),
    ),
    Detector(
        "fake_success",
        "social_engineering",
        "Fake success stories",
        15,
        "Uses screenshots, testimonials or lifestyle flexing as 'proof' - easily faked.",
        (
            r"\b(i|he|she|my (student|client|friend)s?)\s+(made|earned|turned|got)\b.{0,30}\b(₹|rs\.?|inr|lakh|crore|\d)",
            r"\b(profit|payment|withdrawal)\s+(proof|screenshot)s?\b",
            r"\b(testimonial|success stor(y|ies)|real results|see my results)\b",
            r"\bfrom\s+(₹|rs\.?)?\s*\d[\d,]*\s*(k|lakh)?\s+to\s+(₹|rs\.?)?\s*\d[\d,]*\s*(k|lakh|crore)\b",
        ),
    ),
    Detector(
        "payment_request",
        "social_engineering",
        "Unusual payment request",
        20,
        "Asks for upfront fees, payment to a personal UPI ID, or crypto/gift-card transfer.",
        (
            r"\b(registration|processing|joining|activation|tax|release|clearance)\s+(fee|charge|amount)s?\b",
            r"\b(pay|send|transfer|deposit|bhej(o| do)?)\b.{0,30}\b(upi|gpay|google pay|phonepe|paytm|usdt|bitcoin|crypto|gift card|wallet)\b",
            r"\b[a-z0-9._-]{2,}@(ok(sbi|axis|icici|hdfcbank)|ybl|ibl|axl|paytm|upi|apl|fbl)\b",
            r"\b(task|like|review|rating)[- ]based\s+(job|income|earning)|work from home.{0,30}(earn|daily)\b",
        ),
    ),
    Detector(
        "advance_fee",
        "social_engineering",
        "Upfront fee to release money",
        40,
        "Asks you to pay a fee, tax or charge before you can receive a prize, loan, refund, job or parcel - a classic advance-fee fraud.",
        (
            r"\b(pay|send|deposit|transfer)\b.{0,50}\b(fee|fees|charges?|tax|gst|duty|deposit)\b.{0,50}\b(claim|receive|release|collect|unlock|activate|disburs\w*|get (your|the)|to get)\b",
            r"\b(fee|charges?|tax|gst|duty)\b.{0,15}\bto\s+(claim|receive|release|collect|unlock)\b",
            r"\b(processing|registration|shipping|customs|clearance|release|insurance|redelivery|delivery|activation)\s+(fee|charges?|duty)\b.{0,60}\b(prize|loan|refund|parcel|gift|kit|job|disburs\w*|claim|collect|release|lottery)\b",
            r"\b(prepa(y|id)|pay first|advance payment)\b",
        ),
    ),
    Detector(
        "task_scam",
        "social_engineering",
        "Task / part-time job scam",
        40,
        "Offers money for simple online tasks (likes, reviews, ratings). These 'jobs' later demand deposits that are never returned.",
        (
            r"\b(like|likes|liking|review|reviewing|rate|rating|subscribe)\b.{0,40}\b(videos?|youtube|hotels?|products?|google maps|posts?|restaurants?)\b.{0,60}\b(earn|rs\.?|₹|per|paid|income|commission)\b",
            r"\b(part[- ]time|work from home|online)\s+(job|work|income)\b.{0,60}\b(daily|per day|per task|per review|telegram|whatsapp)\b",
            r"\b(vip|prepaid|merchant)\s+tasks?\b",
        ),
    ),
    Detector(
        "wrong_transfer",
        "social_engineering",
        "'Sent by mistake' refund trick",
        35,
        "Claims money was sent to you by mistake and asks you to return it - usually backed by a fake screenshot or a collect request.",
        (
            r"\b(mistakenly|by mistake|wrongly|accidentally|galti se)\b.{0,40}\b(sent|transferred|credited|bheja|bhej diya)\b",
            r"\b(sent|transferred)\b.{0,30}\b(by mistake|mistakenly|wrongly)\b",
            r"\b(return|send (it )?back|refund|lauta)\b.{0,30}\b(extra|wrong|mistake)",
        ),
    ),
    Detector(
        "payment_deadline",
        "urgency_manipulation",
        "Pay-within-deadline pressure",
        30,
        "Demands a payment within minutes or hours, or else something will be cancelled, blocked or forfeited.",
        (
            r"\b(pay|transfer|deposit|send)\b.{0,50}\b(within|in|before)\s+\d+\s*(minutes?|mins?|hours?|hrs?)\b",
            r"\b(pay|transfer|deposit)\b.{0,60}\b(else|or else|otherwise|failing which)\b",
        ),
    ),
    Detector(
        "secrecy",
        "social_engineering",
        "Secrecy request",
        20,
        "Asks you to keep the request secret from family or the bank - scammers isolate victims so nobody can warn them.",
        (
            r"\b(don'?t|do not|mat|na)\s+(tell|inform|batana|bataana)\b.{0,20}\b(anyone|family|bank|kisi)\b",
            r"\bkisi\s+ko\s+(mat|na)\s+bata",
            r"\b(keep (this|it) (secret|confidential)|between (you and me|us))\b",
        ),
    ),
    Detector(
        "missing_disclosure",
        "fake_advisor",
        "Missing regulatory disclosures",
        10,
        "Investment pitch without a SEBI registration number or standard risk disclaimer.",
        (r"\b(invest|investment|trading|scheme|plan|portfolio)\b.{0,60}\b(join|dm|whatsapp|telegram|contact)\b",),
    ),
)

# Phrases that, if present, reduce false positives on genuine educational / bank-warning texts.
SAFE_CONTEXT = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bnever share (your )?(otp|pin|cvv|password)\b",
        r"\b(banks?|we|rbi|sebi) (will )?never (ask|call|asks|calls)\b",
        r"\bdo not (share|click|open|install|call)\b",
        r"\bbeware\b",
        r"\b(fraudsters|scammers|cyber ?criminals) (pose|pretend|claim|are|use|often|may|offer)\b",
        r"\bcyber (safety|security|hygiene) (tips?|session|training|awareness)\b",
        r"\b(how to|learn (why|how) to|learn to) (spot|identify|avoid|recogni[sz]e|detect)\b",
        r"\bthere is no such thing\b",
        r"\breport (it |them |fraud )?(to|at|on) (1930|cybercrime)",
        r"\bnever pay to get a job\b",
        r"\binvestments? (in securities market )?(are|is) subject to market risks?\b",
    )
)

SAFE_PRACTICES: dict[str, list[str]] = {
    "guaranteed_returns": [
        "Treat any promise of guaranteed or fixed high returns as a red flag.",
        "Check whether the entity is registered on the SEBI or RBI website before engaging.",
    ],
    "ponzi_scheme": [
        "Avoid schemes where income comes mainly from recruiting new members.",
        "Check RBI's Sachet portal (sachet.rbi.org.in) for unauthorised deposit schemes.",
    ],
    "fake_advisor": [
        "Verify an adviser's SEBI registration number on the SEBI intermediaries list.",
        "Registered advisers never promise returns or share 'sure-shot' tips in chat groups.",
    ],
    "pump_and_dump": [
        "Be wary of sudden hype about little-known stocks or coins on social media.",
        "Coordinated hype is often used to sell to latecomers at inflated prices.",
    ],
    "impersonation": [
        "Contact the organisation directly using contact details from its official website.",
        "Regulators and police do not demand payments or conduct 'digital arrests' over video calls.",
    ],
    "phishing": [
        "Never share OTP, UPI PIN, CVV or passwords with anyone - not even 'bank staff'.",
        "You never need to enter your UPI PIN to receive money.",
        "Do not install screen-sharing or unknown APK apps at a stranger's request.",
    ],
    "urgency_manipulation": [
        "Pause before acting on any message that pressures you to decide immediately.",
        "Discuss the offer with a trusted family member before sending any money.",
    ],
    "social_engineering": [
        "Verify the sender's identity through a separate, trusted channel.",
        "Do not pay 'fees' or 'taxes' upfront to release winnings, loans or refunds.",
    ],
}

GENERAL_PRACTICES = [
    "If you have lost money, call the National Cyber Crime Helpline 1930 or report at cybercrime.gov.in.",
    "Report suspicious numbers and messages on the Sanchar Saathi 'Chakshu' portal.",
]
