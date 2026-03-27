import asyncio
import json
import re
from typing import Any

import groq

import time
import traceback
from config import GROQ_API_KEY, LLM_TIMEOUT, REDIS_TIMEOUT
from knowledge_base import kb
from memory import memory
from prompt import SYSTEM_PROMPT

STATE_IO_TIMEOUT = min(float(REDIS_TIMEOUT), 0.3)


class ConversationManager:
    def __init__(self):
        self.client = groq.AsyncGroq(api_key=GROQ_API_KEY)
        self.model = "llama-3.1-8b-instant" # High-speed free tier
        self._last_response_text = ""  # Track to avoid repeating the same response
        self.response_policy = (
            "Voice response rules: MAXIMUM 2 sentences and MAXIMUM 15 words total. "
            "Use short spoken sentences so TTS starts fast. "
            "Speak like a normal Indian caller in natural Hinglish, not pure Hindi and not pure English. "
            "Write Hindi words in Devanagari script, not romanized Hindi. "
            "Keep product names and common words like Hi, help, course, demo, price, details in English. "
            "Nina is female — use feminine Hindi forms like 'कर सकती हूं'. "
            "Use PERIODS (.) instead of commas (,) to break up text. "
            "No markdown. No lists. No long paragraphs. "
            "Answer directly first. Ask at most one short follow-up question. "
            "NEVER invent course names, pricing, languages, or features not present in context. "
            "If details are unclear, say 'मुझे exact details check करने होंगे' and ask a clarifying question. "
            "Prefer simple spoken words over formal wording. "
            "When relevant, gently guide the user toward booking a free demo."
        )

    def _sanitize_for_tts(self, text: str) -> str:
        cleaned = text.replace("**", " ").replace("*", " ").replace("`", " ")
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned, flags=re.MULTILINE)
        cleaned = re.sub(r"\[(.*?)\]\((.*?)\)", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return self._normalize_hinglish_for_tts(cleaned)

    def _normalize_hinglish_for_tts(self, text: str) -> str:
        replacements = [
            (
                r"\baapke liye kya kar sakta hoon\b|\baapke liye kya kar sakti hoon\b",
                "मैं आपकी कैसे मदद कर सकती हूं",
            ),
            (r"\bnamaste\b", "नमस्ते"),
            (r"\bhello ji\b", "नमस्ते"),
            (r"\bmain\b", "मैं"),
            (r"\bmai\b", "मैं"),
            (r"\bmera\b", "मेरा"),
            (r"\bmeri\b", "मेरी"),
            (r"\bhoon\b", "हूं"),
            (r"\bhun\b", "हूं"),
            (r"\baap\b", "आप"),
            (r"\baapka\b", "आपका"),
            (r"\baapki\b", "आपकी"),
            (r"\baapke\b", "आपके"),
            (r"\baapko\b", "आपको"),
            (r"\bkaise\b", "कैसे"),
            (r"\bliye\b", "लिए"),
            (r"\bmadad\b", "मदद"),
            (r"\bkya\b", "क्या"),
            (r"\bkar\b", "कर"),
            (r"\bsakti\b", "सकती"),
            (r"\bsakta\b", "सकता"),
            (r"\bsakte\b", "सकते"),
            (r"\bkripya\b", "कृपया"),
            (r"\bphir\b", "फिर"),
            (r"\bse\b", "से"),
            (r"\bbatayiye\b", "बताइए"),
            (r"\bbataiye\b", "बताइए"),
            (r"\bboliye\b", "बोलिए"),
            (r"\bbolte\b", "बोलते"),
            (r"\bhain\b", "हैं"),
            (r"\bhaan\b", "हाँ"),
            (r"\bnahi\b", "नहीं"),
            (r"\bbilkul\b", "बिलकुल"),
            (r"\bdhanyavad\b", "धन्यवाद"),
            (r"\bbol rahi hoon\b", "बोल रही हूं"),
            (r"\bchahiye\b", "चाहिए"),
            (r"\bka\b", "का"),
            (r"\bke\b", "के"),
            (r"\bki\b", "की"),
            (r"\baur\b", "और"),
            (r"\bsawaal\b", "सवाल"),
            (r"\bawaaz\b", "आवाज़"),
            (r"\bclear\b", "clear"),
        ]

        normalized = text
        for pattern, replacement in replacements:
            normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    def _rule_based_intent(self, text: str) -> str | None:
        normalized = text.lower().strip()
        original_normalized = normalized  # Keep for ? check
        normalized = normalized.strip(".?!।, ")

        if not normalized:
            return "fallback"

        greeting_words = {
            "hello", "hi", "hey", "good morning", "good afternoon", "good evening",
            "namaste", "नमस्ते", "नमस्कार", "हेलो", "hi ji",
        }
        # Only match as greeting if the entire input is a greeting word/phrase—
        # NOT if the user said more (e.g. "hello. Hi मैं नेहा" has content beyond greeting)
        words = normalized.split()
        if normalized in greeting_words:
            return "greeting"
        # If first word is a greeting but there are ≤2 words total, still greeting
        if len(words) <= 2 and words[0] in greeting_words:
            return "greeting"

        # Confirmations / affirmatives
        confirmation_words = {
            "yes", "okay", "ok", "हां", "हाँ", "जी", "जी हां", "जी हाँ",
            "ठीक है", "theek hai", "bilkul", "बिलकुल", "sure", "yeah",
        }
        if normalized in confirmation_words:
            return "confirmation"

        # Farewells
        if any(w in normalized for w in ["bye", "goodbye", "thank", "thanks", "धन्यवाद", "शुक्रिया", "अलविदा"]):
            return "farewell"

        if any(phrase in normalized for phrase in ["human", "real person", "agent", "manager", "someone real"]):
            if any(word in normalized for word in ["speak", "talk", "transfer", "connect"]):
                return "human_transfer"

        if any(phrase in normalized for phrase in ["book a demo", "book demo", "demo class", "schedule", "book a meeting", "book meeting"]):
            return "book_meeting"

        if any(phrase in normalized for phrase in ["demo", "callback", "call back", "call me", "expert", "counsellor", "counselor"]):
            return "demo_or_callback"

        if "@" in normalized or any(phrase in normalized for phrase in ["i'm interested", "i am interested", "very interested", "my email is", "email me"]):
            return "update_crm"

        direct_question_words = [
            "what", "how", "which", "when", "where", "why",
            "क्या", "कैसे", "कौन", "किस", "कब", "कहाँ", "क्यों",
        ]
        info_request_words = [
            "price", "cost", "fees", "duration", "offer", "offers", "class", "classes",
            "details", "detail", "demo", "callback", "pricing", "syllabus",
            "प्राइस", "फीस", "डिटेल", "जानना", "पता", "बताइए", "बताओ", "चाहिए",
        ]
        if "?" in original_normalized or any(word in normalized for word in direct_question_words):
            return "ask_question"
        if any(word in normalized for word in info_request_words):
            return "ask_question"

        return None

    def _is_short_real_intent(self, text: str) -> bool:
        normalized = text.lower().strip().strip(".?!।, ")
        if not normalized:
            return False
        real_short_intents = {
            "demo", "callback", "yes", "no", "bye", "transfer",
            "डेमो", "callback", "हाँ", "हां", "नहीं", "bye",
        }
        if normalized in real_short_intents:
            return True
        if len(normalized.split()) <= 3 and any(
            token in normalized for token in real_short_intents
        ):
            return True
        return False

    def _clarify_from_text(self, text: str, noise_mode: str) -> str:
        if noise_mode == "noisy":
            return "Awaaz cut ho rahi hai. Course details, fees, ya demo?"
        return "पूरी बात short में बताइए."

    def _shorten_tts_response(self, text: str) -> str:
        """Trim to ≤2 sentences and ≤120 chars for fast TTS."""
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            return text

        # Keep at most 2 sentences
        parts = [part.strip() for part in re.split(r"(?<=[.!?।])\s+", text) if part.strip()]
        text = " ".join(parts[:2]) if parts else text

        # Word-count cap: ≤18 words
        words = text.split()
        if len(words) > 18:
            text = " ".join(words[:18])
            # Re-add period if we cut mid-sentence
            if not text.endswith((".", "?", "!", "।")):
                text += "."

        # Character hard limit
        if len(text) > 120:
            text = text[:117].rstrip() + "..."
        return text

    def _fast_path_response(self, text: str) -> dict[str, Any] | None:
        """Return a canned response dict for common intents, or None to fall through to LLM.
        All responses use proper Hinglish with Devanagari script."""
        normalized = text.lower().strip()

        # --- Empty / noise ---
        if not normalized:
            return {
                "intent": "ambiguity_or_noise",
                "response": "Sorry, आवाज़ clear नहीं आई. Short में फिर बोलिए.",
                "action": "nothing",
            }

        # --- Intent detection ---
        intent = self._rule_based_intent(text)

        # --- How are you ---
        if "how are you" in normalized or "कैसी हो" in normalized or "कैसे हो" in normalized:
            return {
                "intent": "greeting",
                "response": "मैं अच्छी हूं! आपको किस चीज़ में help चाहिए?",
                "action": "nothing",
            }

        # --- Greeting (avoid repeating if we already greeted) ---
        if intent == "greeting":
            # If the last response was already a greeting, don't repeat
            already_greeted = any(
                w in self._last_response_text.lower()
                for w in ["nina", "callindri", "बोल रही"]
            )
            if already_greeted:
                return None  # Fall through to LLM for a fresh response
            return {
                "intent": "greeting",
                "response": "Hi, मैं Nina from Callindri बोल रही हूं. आपको किस चीज़ में help चाहिए?",
                "action": "nothing",
            }

        # --- Human transfer ---
        if intent == "human_transfer":
            return {
                "intent": "human_transfer",
                "response": "मैं आपको expert से connect करवा सकती हूं. Callback चाहेंगे?",
                "action": "transfer",
            }

        # --- Demo booking ---
        if intent == "book_meeting":
            return {
                "intent": "book_meeting",
                "response": "बिलकुल! Free demo arrange कर सकती हूं. आपका preferred time क्या है?",
                "action": "nothing",
            }

        if intent == "demo_or_callback":
            return {
                "intent": "demo_or_callback",
                "response": "ज़रूर. Demo चाहिए या expert callback?",
                "action": "nothing",
            }

        # --- Course / offer questions ---
        if intent == "ask_question" and any(w in normalized for w in ["course", "offer", "class", "कोर्स", "क्लास"]):
            return {
                "intent": "information_request",
                "response": "Course details चाहिए. fees. ya demo? Short में बताइए.",
                "action": "nothing",
            }

        # --- Fees / pricing ---
        if any(w in normalized for w in ["price", "cost", "fees", "fee", "kitna", "कितना", "पैसे", "फीस", "प्राइस", "रुपये"]):
            return {
                "intent": "information_request",
                "response": "Fees के बारे में help कर सकती हूं. Course details. ya demo चाहिए?",
                "action": "nothing",
            }

        # --- Goodbye / thanks ---
        if any(w in normalized for w in ["bye", "goodbye", "thank", "thanks", "धन्यवाद", "शुक्रिया", "अलविदा", "bye bye"]):
            return {
                "intent": "end_call",
                "response": "Thank you! आपका दिन अच्छा रहे. Bye!",
                "action": "end_call",
            }

        # --- Yes / okay / agreement ---
        if normalized.strip(".!।, ") in {"yes", "okay", "ok", "हां", "हाँ", "जी", "जी हां", "जी हाँ", "ठीक है", "theek hai", "bilkul", "बिलकुल", "sure", "yeah"}:
            return {
                "intent": "confirmation",
                "response": "ठीक है. Aap course. fees. demo. किस बारे में पूछना चाहते हैं?",
                "action": "nothing",
            }

        # --- Who are you / kaun ho ---
        if any(phrase in normalized for phrase in ["who are you", "kaun", "कौन हो", "कौन बोल"]):
            return {
                "intent": "greeting",
                "response": "मैं Nina हूं, Callindri की AI assistant. आपकी कैसे help करूं?",
                "action": "nothing",
            }

        return None


    def _format_history(self, history: list[dict]) -> str:
        if not history:
            return "No previous conversation."
        lines = []
        for item in history[-6:]:
            role = item.get("role", "user").capitalize()
            content = item.get("content", "").strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines) if lines else "No previous conversation."

    async def _get_history(self, call_id: str) -> list[dict]:
        try:
            return await asyncio.wait_for(memory.get_history(call_id), timeout=STATE_IO_TIMEOUT)
        except asyncio.TimeoutError:
            return []

    async def _get_knowledge_context(self, text: str, limit: int = 3) -> list[str]:
        try:
            # Re-routing to the modern Async/Semantic knowledge base
            context_str = await kb.search(text, k=limit)
            return [context_str] if context_str else []
        except Exception as exc:
            print(f"[CONVERSATION] knowledge_error={exc}")
            return []

    async def _generate_text(self, messages: list[dict], temperature: float = 0.2) -> str:
        response = await asyncio.wait_for(
            self.client.chat.completions.create(
                messages=messages,
                model=self.model,
                temperature=temperature,
            ),
            timeout=LLM_TIMEOUT,
        )
        return response.choices[0].message.content.strip()

    async def _store_assistant_history(self, call_id: str, response_text: str) -> None:
        try:
            await asyncio.wait_for(
                memory.add_history_message(call_id, "assistant", response_text),
                timeout=STATE_IO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            pass
        except Exception as exc:
            print(f"[CONVERSATION] assistant_history_error={exc}")

    async def process_turn(self, call_id: str, agent_id: str, text: str) -> str:
        fallback_slow = "Ek moment दीजिए. Kripya phir se बताइए."

        try:
            session = await asyncio.wait_for(memory.get_session(call_id), timeout=STATE_IO_TIMEOUT)
            if not session:
                await asyncio.wait_for(
                    memory.create_session(call_id, agent_id),
                    timeout=STATE_IO_TIMEOUT,
                )
        except asyncio.TimeoutError:
            return fallback_slow

        print(f"[CONVERSATION] Turn START | transcript={text!r}")
        t_start = time.time()

        try:
            await asyncio.wait_for(
                memory.add_history_message(call_id, "user", text),
                timeout=STATE_IO_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return fallback_slow

        history = await self._get_history(call_id)

        fast_path = self._fast_path_response(text)
        if fast_path:
            response_text = self._shorten_tts_response(self._sanitize_for_tts(fast_path["response"]))
            if response_text:
                asyncio.create_task(self._store_assistant_history(call_id, response_text))
            print(
                f"[CONVERSATION] Fast-Path Intent={fast_path['intent']} | "
                f"latency={(time.time() - t_start):.2f}s"
            )
            print(
                f"[CONVERSATION] Turn END | total_latency={(time.time() - t_start):.2f}s | "
                f"response={response_text!r}"
            )
            fast_path["response"] = response_text
            self._last_response_text = response_text  # Track for dedup
            fast_path["response"] = response_text
            return fast_path

        knowledge_context = await self._get_knowledge_context(text)
        
        # 2. MEGA-PROMPT (Single LLM Call for Intent + Extraction + Response)
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context: {' '.join(knowledge_context)}\nHistory: {self._format_history(history)}\nUser: {text}"}
        ]

        try:
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    messages=messages,
                    model=self.model,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                ),
                timeout=LLM_TIMEOUT,
            )
            data = json.loads(response.choices[0].message.content)
            
            # Extract basic info for logging
            intent = data.get("intent", "fallback")
            response_text = data.get("response", "I'm sorry, I couldn't process that.")
            action = data.get("action", "nothing")
            
            print(f"[CONVERSATION] Mega-Prompt Intent={intent} | latency={(time.time() - t_start):.2f}s")
            
            # 3. Finalize and Store History
            response_text = self._shorten_tts_response(self._sanitize_for_tts(response_text))
            
            # Enforce hard limit for safety
            if len(response_text) > 120:
                response_text = response_text[:117] + "..."

            asyncio.create_task(self._store_assistant_history(call_id, response_text))

            t_end = time.time()
            print(f"[CONVERSATION] Turn END | total_latency={(t_end - t_start):.2f}s | response={response_text!r}")
            
            self._last_response_text = response_text  # Track for dedup
            data["response"] = response_text
            return data # Return the full JSON object to agent.py

        except Exception as exc:
            print(f"[CONVERSATION] response_error={exc}")
            traceback.print_exc()
            return {"response": "Ek moment दीजिए. Main phir se try karti hoon.", "action": "nothing"}


conversation_manager = ConversationManager()


async def _smoke_test():
    cm = ConversationManager()
    cid = "test_call_123"
    await cm.process_turn(cid, "agent_007", "Hello there")


if __name__ == "__main__":
    asyncio.run(_smoke_test())
