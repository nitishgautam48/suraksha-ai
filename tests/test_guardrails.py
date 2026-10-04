import pytest

from backend.ai.guardrails import is_advice_request, refusal, sanitize_llm_output

ADVICE = [
    "Should I buy Reliance shares now?",
    "Which stock should I invest in this year?",
    "What is the target price for Tata Motors?",
    "Will Nifty go up tomorrow?",
    "Recommend me a good broker",
    "Best mutual fund for 2026?",
    "Give me intraday trading signals",
    "kaunsa share kharidu?",
    "कौन सा शेयर खरीदूं?",
]
SAFE = [
    "How do I report a UPI fraud?",
    "Is this WhatsApp message a scam?",
    "What is an emergency fund?",
    "How can I verify a SEBI registered adviser?",
    "What is a pump and dump scheme?",
]


@pytest.mark.parametrize("q", ADVICE)
def test_advice_requests_detected(q):
    assert is_advice_request(q)


@pytest.mark.parametrize("q", SAFE)
def test_safety_questions_allowed(q):
    assert not is_advice_request(q)


def test_output_with_advice_is_replaced():
    text, blocked = sanitize_llm_output("You should buy this stock, target price 500.", "hi")
    assert blocked and text == refusal("hi")


def test_safe_output_passes_through():
    text, blocked = sanitize_llm_output("Never share your OTP. Call 1930 if defrauded.")
    assert not blocked and "1930" in text
