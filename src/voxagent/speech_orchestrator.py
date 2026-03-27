from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnDecision:
    kind: str
    text: str = ""
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class SpeechOrchestrator:
    """Single authority for deciding whether finalized STT text should
    be accepted, clarified, or ignored.
    """

    _EXACT_ACTIONS = {
        "demo", "callback", "bye", "yes", "no", "transfer",
        "डेमो", "हाँ", "हां", "नहीं",
    }
    _BARE_TOPICS = {
        "course", "courses", "class", "classes", "details", "detail",
        "fees", "fee", "price", "pricing", "कोर्स", "फीस", "प्राइस", "डिटेल",
    }
    _INTERROGATIVES = {
        "what", "how", "which", "when", "where", "why", "who",
        "क्या", "कैसे", "कौन", "किस", "कब", "कहाँ", "क्यों",
    }
    _REQUEST_MARKERS = {
        "जानना", "पता", "बताइए", "बताओ", "चाहिए", "please", "tell", "explain",
        "want", "need", "kitna", "कितना", "how much",
    }
    _CONNECTORS = {
        "में", "से", "के", "की", "का", "को", "तो", "और", "या", "है", "हूं",
        "for", "to", "about", "and", "or", "is", "are",
    }

    def __init__(self, call_id: str):
        self.call_id = call_id
        self.last_tts_text = ""
        self.bot_speaking = False
        self.bot_stopped_at = 0.0
        self._recent_short_fragments: list[float] = []

    def notify_bot_started(self) -> None:
        self.bot_speaking = True

    def notify_bot_stopped(self) -> None:
        self.bot_speaking = False
        self.bot_stopped_at = time.time()

    def notify_assistant_text(self, text: str) -> None:
        self.last_tts_text = text.strip()

    def process_finalized_transcript(self, text: str) -> TurnDecision:
        transcript = " ".join(text.strip().split())
        words = transcript.split()
        metadata = {
            "call_id": self.call_id,
            "word_count": len(words),
            "bot_speaking": self.bot_speaking,
            "seconds_since_bot_stop": round(time.time() - self.bot_stopped_at, 2),
        }
        print(f"[speech_input] transcript={transcript!r} metadata={metadata}")

        if not transcript:
            return self._ignore("empty_transcript", metadata)

        echo_score = self._echo_overlap(transcript)
        metadata["echo_overlap"] = round(echo_score, 2)
        if echo_score >= 0.74:
            return self._ignore("echo_overlap", metadata)

        if time.time() - self.bot_stopped_at < 1.2 and self._looks_fragment(transcript):
            return self._ignore("post_tts_residual_fragment", metadata)

        if self._looks_noise(transcript):
            return self._ignore("noise_only", metadata)

        if self._is_exact_action(transcript):
            return self._accept(transcript, "exact_action", metadata)

        if self._looks_complete(transcript):
            return self._accept(transcript, "complete_request", metadata)

        if self._looks_incomplete(transcript):
            self._note_short_fragment()
            return self._clarify(self._clarification_prompt(), "incomplete_fragment", metadata)

        self._note_short_fragment()
        return self._clarify(self._clarification_prompt(), "ambiguous_transcript", metadata)

    def _accept(self, text: str, reason: str, metadata: dict[str, Any]) -> TurnDecision:
        print(f"[turn_acceptance] kind=accept reason={reason} metadata={metadata}")
        return TurnDecision(kind="accept", text=text, reason=reason, metadata=metadata)

    def _clarify(self, text: str, reason: str, metadata: dict[str, Any]) -> TurnDecision:
        print(f"[turn_acceptance] kind=clarify reason={reason} metadata={metadata}")
        return TurnDecision(kind="clarify", text=text, reason=reason, metadata=metadata)

    def _ignore(self, reason: str, metadata: dict[str, Any]) -> TurnDecision:
        print(f"[turn_acceptance] kind=ignore reason={reason} metadata={metadata}")
        return TurnDecision(kind="ignore", text="", reason=reason, metadata=metadata)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"[\w\u0900-\u097F]+", text.lower())

    def _echo_overlap(self, text: str) -> float:
        if not self.last_tts_text:
            return 0.0
        user_words = {w for w in self._tokenize(text) if len(w) > 1}
        bot_words = {w for w in self._tokenize(self.last_tts_text) if len(w) > 1}
        if not user_words or not bot_words:
            return 0.0
        return len(user_words & bot_words) / max(1, len(user_words))

    def _looks_noise(self, text: str) -> bool:
        cleaned = text.strip(".?!।, ").lower()
        return cleaned in {"uh", "um", "hmm", "haan...", "mm"} or len(cleaned) <= 1

    def _is_exact_action(self, text: str) -> bool:
        cleaned = text.strip(".?!।, ")
        return cleaned.lower() in {x.lower() for x in self._EXACT_ACTIONS}

    def _looks_fragment(self, text: str) -> bool:
        words = text.strip().strip(".?!।,").split()
        if len(words) <= 2:
            return True
        last = words[-1].lower()
        return last in self._CONNECTORS

    def _looks_incomplete(self, text: str) -> bool:
        stripped = text.strip()
        lowered = stripped.lower()
        words = stripped.strip(".?!।,").split()
        if not words:
            return True
        if len(words) <= 2 and not self._is_exact_action(stripped):
            return True
        if words[-1].lower() in self._CONNECTORS:
            return True
        if any(topic == lowered for topic in self._BARE_TOPICS):
            return True
        if any(phrase in lowered for phrase in ["के बारे में", "ke baare mein", "about"]):
            if not any(marker in lowered for marker in self._REQUEST_MARKERS):
                return True
        if len(words) <= 4 and not stripped.endswith(("?", "!", "।")):
            if not any(marker in lowered for marker in self._REQUEST_MARKERS):
                return True
        return False

    def _looks_complete(self, text: str) -> bool:
        stripped = text.strip()
        lowered = stripped.lower()
        words = stripped.strip(".?!।,").split()
        if stripped.endswith(("?", "!", "।")):
            return True
        if any(token in lowered for token in self._INTERROGATIVES):
            return True
        if any(marker in lowered for marker in self._REQUEST_MARKERS) and len(words) >= 4:
            return True
        if len(words) >= 7:
            return True
        return False

    def _note_short_fragment(self) -> None:
        now = time.time()
        self._recent_short_fragments.append(now)
        self._recent_short_fragments = [ts for ts in self._recent_short_fragments if now - ts <= 20]

    def _clarification_prompt(self) -> str:
        if len(self._recent_short_fragments) >= 2:
            return "Awaaz cut ho rahi hai. Course details, fees, ya demo?"
        return "पूरी बात short में बताइए."
