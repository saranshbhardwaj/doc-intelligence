"""Low-signal message detection for chat.

Identifies acknowledgements, greetings, thanks, and farewells that don't
need RAG retrieval — saving latency and compute.
"""
import re

_ACK_WORDS = {
    "ok", "okay", "k", "kk", "alright", "sure", "sounds", "good", "cool", "great",
    "perfect", "awesome", "nice", "fine", "got", "it", "understood", "yep", "yes",
    "no", "thanks", "thank", "you", "thx", "appreciate", "appreciated",
    "hi", "hello", "hey", "bye", "goodbye", "later", "cheers"
}
_GREETING_WORDS = {"hi", "hello", "hey"}
_THANKS_WORDS = {"thanks", "thank", "thx", "appreciate", "appreciated"}
_FAREWELL_WORDS = {"bye", "goodbye", "later", "cheers"}


def is_low_signal_message(user_message: str) -> bool:
    if not user_message:
        return False
    msg = user_message.strip().lower()
    if not msg or len(msg) > 50:
        return False
    if "?" in msg:
        return False
    if re.search(r"\d", msg):
        return False
    normalized = re.sub(r"[^a-z\s]", " ", msg)
    words = [w for w in normalized.split() if w]
    if not words:
        return False
    return all(w in _ACK_WORDS for w in words)


def low_signal_response(user_message: str) -> str:
    msg = (user_message or "").strip().lower()
    if any(w in msg for w in _THANKS_WORDS):
        return "You're welcome! Let me know if you'd like me to analyze anything else."
    if any(w in msg for w in _FAREWELL_WORDS):
        return "Got it. If you need anything else, just ask."
    if any(w in msg for w in _GREETING_WORDS):
        return "Hi! What would you like to know about these documents?"
    return "Okay. Let me know if you'd like anything else."
