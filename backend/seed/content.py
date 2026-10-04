"""Curated starter curriculum for the Learning Center (no investment advice)."""

from __future__ import annotations

COURSES = [
    {
        "slug": "scam-detection-101",
        "title": "Spot Investment Scams",
        "topic": "scam_detection",
        "level": "beginner",
        "description": "Learn the red flags of Ponzi schemes, fake advisers, pump-and-dump groups and guaranteed-return offers.",
        "lessons": [
            (
                "Why 'guaranteed returns' is the biggest red flag",
                4,
                """
All market-linked investments carry risk, so **no one can honestly guarantee returns**. SEBI-registered
entities are not allowed to promise them.

**Red flags**
- "Assured 5% monthly", "double your money in 90 days", "zero risk"
- Returns that never go down, whatever the market does
- Pressure to reinvest instead of withdrawing

**Key takeaways**
- High return + no risk = contradiction.
- Verify registrations on sebi.gov.in or rbi.org.in before trusting any offer.
""",
            ),
            (
                "Ponzi and pyramid schemes",
                5,
                """
A Ponzi scheme pays old investors with new investors' money. It collapses when new money stops.

**Warning signs**
- Referral, level or "team" income
- Secret "AI trading bot" or "forex robot" that no one can verify
- New "fees" or "taxes" when you try to withdraw

Unregulated deposit schemes are banned under the Banning of Unregulated Deposit Schemes Act, 2019.
Report them on RBI's **Sachet** portal.

**Key takeaways**
- If income depends on recruiting others, walk away.
- Keep records and report to 1930 if you have paid.
""",
            ),
            (
                "Fake advisers and pump-and-dump groups",
                5,
                """
"VIP tips" groups on WhatsApp and Telegram often run **pump-and-dump** schemes: operators buy a
little-known stock, hype it ("multibagger", "operator buying", "upper circuit"), then sell to latecomers.

**Protect yourself**
- Ask for the SEBI registration number and verify it on the SEBI website.
- Registered advisers never promise returns or "sure-shot" calls.
- Ignore unsolicited stock hype.

**Key takeaways**
- Unregistered tips are not advice.
- Hype + urgency + little-known stock = pump-and-dump pattern.
""",
            ),
        ],
        "flashcards": [
            (
                "Can any investment guarantee high returns?",
                "No. Market-linked investments carry risk; guaranteed high returns are a red flag.",
            ),
            (
                "What is a Ponzi scheme?",
                "A fraud that pays earlier investors with money from new investors instead of real profits.",
            ),
            (
                "How do you verify an investment adviser?",
                "Check their SEBI registration number on the SEBI 'Recognised Intermediaries' list.",
            ),
            (
                "What is a pump-and-dump?",
                "Operators hype a thinly traded stock, then sell their holdings to people who buy on the hype.",
            ),
            ("Where can you report illegal deposit schemes?", "RBI's Sachet portal (sachet.rbi.org.in)."),
            ("What number do you call after losing money to fraud?", "1930 - the National Cyber Crime Helpline."),
        ],
        "questions": [
            (
                "A message promises '3% guaranteed monthly returns, zero risk'. What is this most likely?",
                ["A safe fixed deposit", "A red flag for a scam", "A SEBI-approved product", "A government bond"],
                1,
                "No legitimate investment can guarantee returns with zero risk.",
            ),
            (
                "Which feature is typical of a Ponzi scheme?",
                [
                    "Audited financial statements",
                    "Income from recruiting new members",
                    "Clear risk disclosures",
                    "Regulator registration",
                ],
                1,
                "Ponzi and pyramid schemes depend on new money from recruitment.",
            ),
            (
                "Before following an 'investment guru', you should:",
                [
                    "Check their follower count",
                    "Verify their SEBI registration",
                    "Join their paid VIP group",
                    "Ask for profit screenshots",
                ],
                1,
                "Only SEBI-registered advisers may give paid investment advice.",
            ),
            (
                "'Operator buying, multibagger, buy before Monday!' is an example of:",
                ["Research report", "Pump language", "Regulatory notice", "Risk disclosure"],
                1,
                "Hype plus urgency about a little-known stock is a pump-and-dump pattern.",
            ),
            (
                "You're asked to pay a 'tax' to withdraw your profits from an app. You should:",
                ["Pay quickly", "Borrow money to pay", "Stop and report it to 1930", "Recruit friends to cover it"],
                2,
                "Withdrawal 'fees' are a classic sign of a fake trading app.",
            ),
        ],
    },
    {
        "slug": "upi-fraud-safety",
        "title": "UPI Fraud Safety",
        "topic": "upi_frauds",
        "level": "beginner",
        "description": "Stay safe with UPI: PIN rules, collect requests, QR codes, fake screenshots and fake helplines.",
        "lessons": [
            (
                "You never need a PIN to receive money",
                3,
                """
Entering your **UPI PIN always sends money out** of your account.

If someone says "enter your PIN to receive the refund / prize / payment", it is a scam.

**Key takeaways**
- PIN = paying.
- Decline collect requests you don't recognise.
""",
            ),
            (
                "QR codes, collect requests and fake screenshots",
                4,
                """
- **QR codes** are scanned to *pay*, not to receive.
- **Collect requests** can be disguised as refunds. Approving one sends money away.
- **Fake screenshots**: scammers show an edited "payment done" image and ask you to return the "extra".
  Always check your bank app, not the screenshot.

**Key takeaways**
- Verify the payee name before entering your PIN.
- Trust your bank statement, not images.
""",
            ),
            (
                "Fake customer care and what to do after fraud",
                4,
                """
Fraudsters post fake helpline numbers online. Use help only from the official app or website.

**If you are defrauded**
1. Call **1930** immediately and report at cybercrime.gov.in.
2. Inform your bank and block UPI/cards.
3. Under RBI rules, reporting an unauthorised transaction within 3 working days can limit your liability.

**Key takeaways**
- Speed matters - report within minutes, not days.
""",
            ),
        ],
        "flashcards": [
            ("Do you need your UPI PIN to receive money?", "Never. The PIN is only used to send money."),
            ("Is scanning a QR code a way to receive money?", "No - scanning a QR code is for paying."),
            ("What is a collect-request scam?", "A fake 'refund' request that actually debits your account when you approve it."),
            ("Where should you find a customer-care number?", "Only inside the official app or on the official website."),
            ("What should you do first after UPI fraud?", "Call 1930 and your bank immediately."),
        ],
        "questions": [
            (
                "A buyer sends a QR code so you can 'receive' payment. You should:",
                ["Scan and enter PIN", "Refuse - QR codes are used to pay", "Share your UPI ID and PIN", "Send a test rupee"],
                1,
                "Scanning a QR code and entering a PIN sends money out.",
            ),
            (
                "When do you need to enter your UPI PIN?",
                ["To receive money", "To send money", "To check messages", "Never"],
                1,
                "PIN authorises debits only.",
            ),
            (
                "Someone shows a screenshot of an extra payment and asks you to return it. You should:",
                ["Return immediately", "Check your actual bank balance/statement first", "Send double", "Share OTP"],
                1,
                "Screenshots are easily edited.",
            ),
            (
                "The fastest helpline for reporting cyber financial fraud in India is:",
                ["100", "1930", "112", "1098"],
                1,
                "1930 is the National Cyber Crime Helpline.",
            ),
        ],
    },
    {
        "slug": "cyber-safety-essentials",
        "title": "Cyber Safety Essentials",
        "topic": "cyber_safety",
        "level": "beginner",
        "description": "Phishing links, remote-access apps, digital-arrest scams, deepfakes and safe phone habits.",
        "lessons": [
            (
                "Phishing links and look-alike websites",
                4,
                """
Phishing messages copy logos and use look-alike domains such as `sbi-kyc-update.xyz`.

**Check before you click**
- Extra words like *kyc, verify, reward* in the domain
- Unusual endings (.xyz, .top, .click) and shortened links
- Requests for OTP, PIN, CVV or passwords

**Key takeaways**
- Type official addresses yourself.
- Banks never ask for OTP or PIN.
""",
            ),
            (
                "'Digital arrest' and impersonation scams",
                4,
                """
Fraudsters pose as police, CBI or customs on video calls and demand money to "clear your name".

**There is no 'digital arrest' in Indian law.** Real officials do not interrogate people on video calls
or ask for transfers.

**Key takeaways**
- Disconnect, do not pay, report to 1930.
- Verify any claim through official numbers you find yourself.
""",
            ),
            (
                "Remote-access apps, APKs and deepfakes",
                4,
                """
- Never install screen-sharing apps (AnyDesk, TeamViewer) or APK files at a stranger's request.
- AI deepfake videos of celebrities may "endorse" fake schemes - verify independently.
- Report suspicious calls/SMS on **Sanchar Saathi - Chakshu**.

**Key takeaways**
- Your screen and your OTP are keys to your money.
""",
            ),
        ],
        "flashcards": [
            (
                "Is 'digital arrest' a real legal procedure?",
                "No. It is a scam; real agencies don't arrest people over video calls.",
            ),
            (
                "Name two signs of a phishing link.",
                "Look-alike domain with words like 'kyc'/'verify', unusual TLD, or a shortened URL.",
            ),
            (
                "Should you install AnyDesk for a caller from 'the bank'?",
                "Never - remote-access apps let fraudsters control your phone.",
            ),
            ("Where can you report fraud calls and SMS?", "Sanchar Saathi portal's Chakshu facility."),
        ],
        "questions": [
            (
                "Which domain is most likely phishing?",
                ["onlinesbi.sbi", "sbi-kyc-verify.xyz", "rbi.org.in", "sebi.gov.in"],
                1,
                "It uses the bank's name plus lure words on a low-cost TLD.",
            ),
            (
                "A 'CBI officer' on video call says you're under digital arrest. You should:",
                ["Stay on call and pay", "Disconnect and report to 1930", "Share Aadhaar", "Transfer to a 'safe account'"],
                1,
                "Digital arrest is a scam.",
            ),
            (
                "A caller asks you to install a screen-sharing app to fix your KYC. This is:",
                ["Normal bank procedure", "A remote-access fraud", "Required by RBI", "Safe if quick"],
                1,
                "Banks never need control of your device.",
            ),
        ],
    },
    {
        "slug": "financial-literacy-foundations",
        "title": "Money Habits Foundations",
        "topic": "financial_literacy",
        "level": "beginner",
        "description": "Emergency funds, budgeting, saving discipline, risk vs return and borrowing safely. No product advice.",
        "lessons": [
            (
                "Build an emergency fund",
                4,
                """
An emergency fund is money kept aside and easy to access for unexpected events.
A common guideline is to build up **3 to 6 months of essential expenses** over time.

**Why it matters**
- Protects you from panic decisions and high-cost loans
- Makes "quick money" scam offers less tempting during a crisis

**Key takeaways**
- Start small; consistency beats amount.
""",
            ),
            (
                "Budgeting and paying yourself first",
                4,
                """
1. Track income and expenses for one month.
2. Separate needs from wants.
3. Set aside savings as soon as income arrives ("pay yourself first").

**Key takeaways**
- Regular small savings build discipline and resilience.
""",
            ),
            (
                "Risk, return and borrowing safely",
                4,
                """
Higher potential return always comes with higher risk. "High return, no risk" is a contradiction.

Borrow only from regulated lenders (banks, RBI-registered NBFCs). Avoid loan apps that demand access
to your contacts and photos.

For personal investment advice, consult only a **SEBI-registered Investment Adviser**.

**Key takeaways**
- Understand before you commit; verify before you trust.
""",
            ),
        ],
        "flashcards": [
            (
                "What is an emergency fund?",
                "Easily accessible money set aside for unexpected events like job loss or medical needs.",
            ),
            ("Common emergency fund guideline?", "Build up 3-6 months of essential expenses over time."),
            ("What does 'pay yourself first' mean?", "Set aside savings as soon as income arrives, before spending."),
            ("High return with no risk is…", "A contradiction and a warning sign."),
        ],
        "questions": [
            (
                "Why is an emergency fund useful?",
                ["To trade daily", "To handle unexpected expenses without panic", "To lend to friends", "To buy tips"],
                1,
                "It provides resilience during emergencies.",
            ),
            (
                "'Pay yourself first' means:",
                ["Spend first, save leftovers", "Save as soon as income arrives", "Borrow to save", "Avoid budgeting"],
                1,
                "Prioritising savings builds discipline.",
            ),
            (
                "Who should you consult for personal investment advice?",
                ["A Telegram tips group", "A SEBI-registered Investment Adviser", "An influencer", "A random caller"],
                1,
                "Only registered advisers are regulated.",
            ),
        ],
    },
]
