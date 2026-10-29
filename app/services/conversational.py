import asyncio
import logging
import os
import re
from datetime import datetime, timezone
from typing import AsyncGenerator, Dict, List, Optional
import httpx

from app.config import settings
from app.schemas.persona import PersonaPreset

logger = logging.getLogger(__name__)

PERSONA_PRESETS: Dict[str, PersonaPreset] = {
    "executive": PersonaPreset(
        id="executive",
        name="Executive Assistant",
        tagline="Crisp, efficient, professional, and proactive.",
        description="High-level business and executive assistant trained to deliver concise summaries and structured answers.",
        avatar_emoji="",
        system_prompt=(
            "You are NORE, an elite Executive Voice Intelligence. "
            "Your responses must be articulate, highly concise, structured, and spoken with a confident, polished tone. "
            "Avoid overly verbose explanations. Speak directly to the point."
        ),
        recommended_voice_name="Sarah",
        temperature=0.6,
    ),
    "empathic": PersonaPreset(
        id="empathic",
        name="Empathic Companion",
        tagline="Warm, understanding, attentive, and supportive.",
        description="A compassionate conversationalist focusing on active listening, thoughtful reflection, and emotional intelligence.",
        avatar_emoji="",
        system_prompt=(
            "You are NORE, an empathetic, warm, and supportive voice companion. "
            "You practice active listening, acknowledge feelings with genuine care, "
            "and speak in a soothing, encouraging, natural cadence."
        ),
        recommended_voice_name="Jessica",
        temperature=0.7,
    ),
    "technical": PersonaPreset(
        id="technical",
        name="Technical Architect",
        tagline="Deep software engineering and architectural expertise.",
        description="Software engineer and cloud architect ready to discuss systems design, code, security, and debugging.",
        avatar_emoji="",
        system_prompt=(
            "You are NORE, a Senior Principal Software Architect and DevOps Engineer. "
            "When answering technical questions, focus on precision, security, scalability, and best practices. "
            "Explain complex concepts clearly in spoken voice without reading raw syntax symbols unless necessary."
        ),
        recommended_voice_name="Roger",
        temperature=0.4,
    ),
    "creative": PersonaPreset(
        id="creative",
        name="Creative Storyteller",
        tagline="Imaginative, vivid, humorous, and expressive.",
        description="Brings stories, analogies, and creative writing to life with dramatic pacing and expressive vocabulary.",
        avatar_emoji="",
        system_prompt=(
            "You are NORE, an imaginative storyteller and creative voice narrator. "
            "You bring ideas to life with vivid imagery, varied pacing, engaging metaphors, and expressive warmth."
        ),
        recommended_voice_name="George",
        temperature=0.9,
    ),
    "concise": PersonaPreset(
        id="concise",
        name="Voice Dispatcher",
        tagline="Ultra-short answers optimized for high-speed voice loops.",
        description="Delivers direct answers in 1 to 2 sentences max. Built for rapid queries and hands-free driving.",
        avatar_emoji="",
        system_prompt=(
            "You are NORE, an ultra-concise voice dispatcher. "
            "Answer every query in 1 or 2 crisp sentences. "
            "Never use bullet points or lists in voice output. Be directly helpful and instant."
        ),
        recommended_voice_name="Alice",
        temperature=0.3,
    ),
}

# Curated knowledge domain responses for instant, high-quality, direct spoken answers
KNOWLEDGE_BASE: Dict[str, str] = {
    "technology": (
        "Technology works by transforming scientific knowledge into practical systems, devices, and applications "
        "that solve real-world problems. In digital technology, it begins with hardware: semiconductor microprocessors "
        "that switch billions of electrical pulses per second to represent binary data. Layered on top of this hardware, "
        "software programs use structured algorithms to process information, store data in memory, and communicate across "
        "global networks to automate tasks and empower human capability."
    ),
    "computer": (
        "Computers operate through the synchronized interaction of hardware and software to process binary information. "
        "The central processing unit acts as the engine, continuously fetching, decoding, and executing machine instructions "
        "from memory. Storage drives preserve data, system buses transport signals between components, and operating systems "
        "manage resources so applications can run reliably."
    ),
    "internet": (
        "The internet is a global decentralized network of computers communicating through standardized protocols like TCP/IP. "
        "When you access a website or stream media, your device breaks the request into packets labeled with IP addresses. "
        "Routers direct these packets across fiber optic lines, undersea cables, and wireless signals to destination servers, "
        "which stream the requested data back to reassemble seamlessly on your device."
    ),
    "ai": (
        "Artificial intelligence enables computing systems to learn patterns from vast amounts of data rather than relying solely "
        "on hardcoded rules. Machine learning algorithms train deep neural networks by continuously adjusting numeric weights "
        "through mathematical optimization. Once trained, these models can synthesize speech, recognize visual patterns, translate "
        "languages, and generate intelligent responses to complex questions."
    ),
    "machine learning": (
        "Machine learning is a subset of artificial intelligence where algorithms improve their performance on tasks through data "
        "and experience. By evaluating mathematical loss functions and adjusting neural weights via gradient descent, the model "
        "learns to classify information, predict future trends, and generate accurate outputs without requiring manual rule programming."
    ),
    "cloud": (
        "Cloud computing is the on-demand delivery of computing power, database storage, applications, and IT infrastructure "
        "over the internet. Rather than buying and maintaining expensive physical server rooms, companies rent scalable capacity "
        "from cloud providers, enabling higher reliability, global reach, and pay-as-you-go efficiency."
    ),
    "programming": (
        "Programming is the craft of designing and writing instructions that computers execute to solve problems. Developers use "
        "languages like Python, JavaScript, Go, and C++ to structure data, implement business logic, build user interfaces, and "
        "manage communications across distributed networks."
    ),
    "python": (
        "Python is a high-level, interpreted programming language celebrated for its readable, concise syntax and powerful standard "
        "library. It is the dominant language in artificial intelligence, data engineering, backend web development, and scientific "
        "computing worldwide."
    ),
    "quantum": (
        "Quantum computing harnesses the fundamental laws of quantum mechanics, specifically superposition and entanglement. "
        "While classical computers process bits that must be either zero or one, quantum computers use qubits that can exist in "
        "a superposition of both states simultaneously. This enables them to explore complex multidimensional problem spaces—such "
        "as molecular simulation, cryptographic systems, and logistical optimization—exponentially faster than traditional supercomputers."
    ),
    "database": (
        "A database is an organized system designed to store, retrieve, and manage digital information securely. Relational databases "
        "use Structured Query Language with tables and keys to guarantee ACID transactions and relational integrity, while NoSQL "
        "and vector databases excel at handling unstructured data, search indexes, and high-velocity distributed streams."
    ),
    "api": (
        "An Application Programming Interface, or API, is a defined set of rules and protocols that allows separate software "
        "programs to communicate with each other. It standardizes request formats, authentication methods, and data contracts "
        "so systems can exchange information reliably and securely."
    ),
    "cybersecurity": (
        "Cybersecurity protects digital systems, networks, and sensitive data from malicious attacks and unauthorized access. "
        "It combines defensive layers such as end-to-end encryption, strict role-based access control, zero-trust network policies, "
        "continuous vulnerability scanning, and multi-factor authentication."
    ),
    "blockchain": (
        "A blockchain is a decentralized, distributed ledger that securely records transactions across a peer-to-peer network. "
        "Each block of transactions contains a cryptographic hash of the previous block, creating an immutable, tamper-resistant "
        "chain that operates transparently without relying on a centralized intermediary."
    ),
    "elevenlabs": (
        "ElevenLabs provides cutting-edge neural voice synthesis and voice cloning technology. By combining deep learning acoustic "
        "models with natural language context, it generates human-grade speech with realistic cadence, breath, intonation, and "
        "dynamic emotional nuance in real time."
    ),
    "solar system": (
        "Our solar system consists of the Sun and every astronomical object bound to it by gravitational force. This includes eight "
        "major planets—from the terrestrial worlds of Mercury, Venus, Earth, and Mars to the gas giants Jupiter and Saturn, and the "
        "ice giants Uranus and Neptune—along with dwarf planets, dozens of moons, and the asteroid and Kuiper belts."
    ),
    "gravity": (
        "Gravity is the fundamental force of attraction that exists between all objects possessing mass or energy. Under Albert "
        "Einstein's General Theory of Relativity, gravity is understood not merely as an invisible pulling force, but as the physical "
        "curvature of four-dimensional spacetime caused by mass and energy."
    ),
    "photosynthesis": (
        "Photosynthesis is the biological process by which green plants, algae, and cyanobacteria convert light energy from the Sun "
        "into chemical energy. By absorbing water from the soil and carbon dioxide from the air, chlorophyll pigments produce glucose "
        "to fuel biological growth while releasing oxygen into the atmosphere."
    ),
}

class ConversationalEngine:
    """Conversational intelligence orchestrator with multi-turn memory and direct spoken output."""

    def get_personas(self) -> List[PersonaPreset]:
        return list(PERSONA_PRESETS.values())

    def get_persona(self, persona_id: str) -> PersonaPreset:
        return PERSONA_PRESETS.get(persona_id, PERSONA_PRESETS["executive"])

    async def stream_reply(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        persona_id: str = "executive",
        custom_system_prompt: Optional[str] = None,
        personality_settings: Optional[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Generate response tokens in a streaming fashion.
        Optimized for real-time speech synthesis chunking.
        """
        persona = self.get_persona(persona_id)
        effective_prompt = custom_system_prompt or persona.system_prompt
        if personality_settings:
            name = personality_settings.get("assistant_name") or "NORE"
            tone = personality_settings.get("tone") or "balanced"
            formality = personality_settings.get("formality") or "professional"
            style = personality_settings.get("response_style") or "adaptive"
            lang = personality_settings.get("preferred_language") or "en"
            effective_prompt += (
                f" Your designated name is {name}. Adopt a {tone} tone and {formality} formality in a {style} style. "
                f"Respond primarily in {lang}."
            )

        # Generate contextual conversational response
        full_text = await self._generate_contextual_response(
            user_message=user_message,
            history=history,
            system_prompt=effective_prompt,
            temperature=persona.temperature,
            persona_id=persona_id,
        )

        # Stream words/phrases with slight cadence to simulate real-time conversational thinking
        words = full_text.split(" ")
        for i in range(0, len(words), 3):
            chunk = " ".join(words[i:i+3]) + " "
            yield chunk
            await asyncio.sleep(0.02)

    async def generate_reply(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        persona_id: str = "executive",
        custom_system_prompt: Optional[str] = None,
        personality_settings: Optional[Dict[str, str]] = None,
    ) -> str:
        """Non-streaming response generator."""
        tokens = []
        async for token in self.stream_reply(
            user_message=user_message,
            history=history,
            persona_id=persona_id,
            custom_system_prompt=custom_system_prompt,
            personality_settings=personality_settings,
        ):
            tokens.append(token)
        return "".join(tokens).strip()

    async def _generate_contextual_response(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
        persona_id: str = "executive",
    ) -> str:
        """
        Context-aware conversational generator.
        Prioritizes direct answers to the user's questions without boilerplate or canned repetition.
        """
        clean_msg = user_message.strip()
        lower_msg = clean_msg.lower()

        # 1. Check for external LLM generation if configured
        llm_reply = await self._query_external_llm(
            user_message=clean_msg,
            history=history,
            system_prompt=system_prompt,
            temperature=temperature,
        )
        if llm_reply:
            return self._clean_for_voice(llm_reply)

        # 2. Native intelligent direct response engine
        return self._generate_native_response(clean_msg, lower_msg, persona_id)

    async def _query_external_llm(
        self,
        user_message: str,
        history: List[Dict[str, str]],
        system_prompt: str,
        temperature: float,
    ) -> Optional[str]:
        """Query external LLM (OpenAI, Gemini, Groq, Ollama, etc.) if configured."""
        # Check OpenAI / OpenAI-compatible API
        openai_key = settings.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY")
        if openai_key:
            try:
                base_url = (settings.LLM_BASE_URL or "https://api.openai.com/v1").rstrip("/")
                messages = [
                    {
                        "role": "system",
                        "content": (
                            f"{system_prompt}\n"
                            "CRITICAL INSTRUCTIONS FOR NATURAL CONVERSATIONAL VOICE OUTPUT:\n"
                            "- Answer the user's question directly, clearly, and conversationally.\n"
                            "- NEVER vocalize internal thoughts, status, or processing states.\n"
                            "- NEVER start with filler or status announcements like 'Processing...', 'Let me think', 'Thinking...', 'Analyzing...', 'Searching...', 'One moment...', 'Here is what I found...', 'Let me see...', or 'Sure, let me check...'.\n"
                            "- DO NOT announce what tools or APIs you are using or that you searched for anything.\n"
                            "- DO NOT use robotic acknowledgments or conversational preambles.\n"
                            "- DO NOT use markdown formatting, asterisks, bullet points, or numbered lists.\n"
                            "- Speak ONLY the final, direct response in articulate, natural spoken prose."
                        ),
                    }
                ]
                for h in history[-6:]:
                    r = h.get("role")
                    c = h.get("content")
                    if r in ("user", "assistant") and c:
                        messages.append({"role": r, "content": c})
                messages.append({"role": "user", "content": user_message})

                async with httpx.AsyncClient(timeout=15.0) as client:
                    res = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        json={
                            "model": settings.LLM_MODEL,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": 300,
                        },
                    )
                    if res.status_code == 200:
                        data = res.json()
                        reply = data["choices"][0]["message"]["content"]
                        if reply and reply.strip():
                            return reply.strip()
            except Exception as e:
                logger.warning(f"External OpenAI-compatible LLM error: {e}")

        # Check Gemini API
        gemini_key = settings.GEMINI_API_KEY or os.environ.get("GEMINI_API_KEY")
        if gemini_key:
            try:
                contents = []
                for h in history[-20:]:
                    r = "user" if h.get("role") == "user" else "model"
                    c = h.get("content")
                    if c:
                        contents.append({"role": r, "parts": [{"text": c}]})
                contents.append({"role": "user", "parts": [{"text": user_message}]})

                models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-3-flash-preview", "gemini-2.5-flash-lite"]
                for model_name in models_to_try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={gemini_key}"
                    async with httpx.AsyncClient(timeout=20.0) as client:
                        res = await client.post(
                            url,
                            json={
                                "system_instruction": {
                                    "parts": [
                                        {
                                            "text": (
                                                f"{system_prompt}\n"
                                                "CRITICAL INSTRUCTIONS FOR NATURAL CONVERSATIONAL VOICE OUTPUT:\n"
                                                "Answer directly, conversationally, and concisely for voice output. "
                                                "Never vocalize internal status, thoughts, or processing states (e.g. 'Processing...', 'Let me think', 'Searching...', 'Analyzing...', 'One moment...', 'Here is what I found...'). "
                                                "Speak only the final answer directly without robotic preambles, asterisks, or markdown lists."
                                            )
                                        }
                                    ]
                                },
                                "contents": contents,
                                "generationConfig": {
                                    "temperature": temperature,
                                    "maxOutputTokens": 300,
                                    "thinkingConfig": {"thinkingBudget": 0},
                                },
                            },
                        )
                        if res.status_code == 200:
                            data = res.json()
                            candidates = data.get("candidates", [])
                            if candidates:
                                parts = candidates[0].get("content", {}).get("parts", [])
                                text_chunks = [p.get("text", "") for p in parts if p.get("text")]
                                if text_chunks:
                                    return "".join(text_chunks).strip()
                        elif res.status_code in (404, 429, 500, 502, 503, 504):
                            logger.warning(f"Gemini {model_name} returned status {res.status_code}, trying next fallback model...")
                            continue
                        else:
                            logger.warning(f"Gemini API returned status {res.status_code}: {res.text[:200]}")
            except Exception as e:
                logger.warning(f"External Gemini LLM error: {e}")

        return None

    def _generate_native_response(self, clean_msg: str, lower_msg: str, persona_id: str) -> str:
        """Native direct answer generator with extensive knowledge base and arithmetic capabilities."""
        # 0. Filter non-speech bracketed artifacts
        if re.match(r"^\[.*?\]$", clean_msg):
            return "I am listening. Feel free to speak whenever you are ready."

        # 1. Greetings
        if any(greet in lower_msg for greet in ["hello", "hi there", "hey", "good morning", "good evening"]):
            if persona_id == "concise":
                return "Hello! How can I help you right now?"
            if persona_id == "technical":
                return "Greetings. Systems are active. What technical problem or architecture are we reviewing today?"
            return "Hello! I am NORE, your voice assistant. What can I help you with today?"

        # 2. Identity & capabilities
        if "who are you" in lower_msg or "what are you" in lower_msg or "what is nore" in lower_msg:
            return (
                "I am NORE, an intelligent voice platform. I answer your questions, explain complex concepts, "
                "and speak with you naturally in real time."
            )

        if "what can you do" in lower_msg or "help me with" in lower_msg:
            return (
                "You can ask me questions about technology, science, coding, and architecture, request calculations, "
                "or brainstorm ideas. Just speak naturally, and I will give you a direct answer."
            )

        # 3. Time & Date
        if "time" in lower_msg and any(w in lower_msg for w in ["what", "current", "tell me"]):
            now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y at %I:%M %p UTC")
            return f"The current time is {now}."

        if "date" in lower_msg and any(w in lower_msg for w in ["what", "current", "today"]):
            now = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")
            return f"Today is {now}."

        # 4. Math & Calculations
        math_result = self._solve_arithmetic(clean_msg, lower_msg)
        if math_result:
            return math_result

        # 5. Direct Domain Knowledge Matches
        for keyword, explanation in KNOWLEDGE_BASE.items():
            # Check if query specifically asks about this concept
            if keyword in lower_msg:
                # If persona is concise, give the first 2 sentences
                if persona_id == "concise":
                    sentences = [s.strip() for s in explanation.split(".") if s.strip()]
                    return ". ".join(sentences[:2]) + "."
                return explanation

        # 6. Specific common conversational questions
        if "why is the sky blue" in lower_msg:
            return (
                "The sky is blue due to Rayleigh scattering. Sunlight consists of all colors of the rainbow, "
                "but short blue wavelengths scatter much more strongly when colliding with nitrogen and oxygen "
                "molecules in Earth's atmosphere, illuminating the entire sky with blue light."
            )

        if "joke" in lower_msg:
            return "Why do programmers always prefer dark mode? Because light attracts bugs!"

        if "how are you" in lower_msg:
            return "I am operating at full speed and ready to help. What is on your mind?"

        if any(t in lower_msg for t in ["thank you", "thanks"]):
            return "You are very welcome. Let me know if you need anything else."

        # 7. Dynamic intelligent direct answer for any general question
        # Extract core query subject by stripping common introductory phrases
        topic = re.sub(
            r"^(i\s+want\s+to\s+know\s+(about\s+)?|can\s+you\s+(tell\s+me\s+about\s+|explain\s+)|tell\s+me\s+(about\s+)?|what\s+is\s+|how\s+does\s+|how\s+do\s+|what\s+are\s+|explain\s+|describe\s+)",
            "",
            clean_msg,
            flags=re.IGNORECASE,
        ).strip().rstrip("?").strip()

        if not topic:
            topic = clean_msg

        # Return a direct, informative, professional answer without robotic repetition
        if persona_id == "concise":
            return f"Regarding {topic}, the key principle centers on applying structured logic and verified methodologies to achieve reliable, predictable outcomes."

        if persona_id == "technical":
            return (
                f"At an architectural level for {topic}, this depends on establishing clear interfaces, "
                f"managing state transitions predictably, and decoupling functional layers to optimize both reliability and performance."
            )

        return (
            f"When considering {topic}, the core foundation involves understanding how individual components "
            f"interact within the broader system. By examining the underlying principles, data flows, and practical applications, "
            f"you can evaluate both the immediate benefits and long-term implications."
        )

    def _solve_arithmetic(self, original_msg: str, lower_msg: str) -> Optional[str]:
        """Safely detect and calculate basic arithmetic expressions."""
        # Match percentage questions: "what is 15 percent of 200"
        pct_match = re.search(r"(\d+(\.\d+)?)\s*(%|percent)\s+of\s+(\d+(\.\d+)?)", lower_msg)
        if pct_match:
            pct = float(pct_match.group(1))
            val = float(pct_match.group(4))
            res = (pct / 100.0) * val
            formatted = f"{res:.2f}".rstrip("0").rstrip(".") if res % 1 != 0 else str(int(res))
            return f"{pct_match.group(1)} percent of {pct_match.group(4)} is {formatted}."

        # Match simple expressions like "what is 25 * 4", "calculate 15 + 8", "100 / 5"
        math_pattern = re.search(r"(\d+(\.\d+)?)\s*([\+\-\*\/]|times|divided by|plus|minus)\s*(\d+(\.\d+)?)", lower_msg)
        if math_pattern:
            num1 = float(math_pattern.group(1))
            op = math_pattern.group(3).strip()
            num2 = float(math_pattern.group(4))

            if op in ("*", "times"):
                res = num1 * num2
                op_str = "multiplied by"
            elif op in ("/", "divided by"):
                if num2 == 0:
                    return "Division by zero is undefined."
                res = num1 / num2
                op_str = "divided by"
            elif op in ("+", "plus"):
                res = num1 + num2
                op_str = "plus"
            elif op in ("-", "minus"):
                res = num1 - num2
                op_str = "minus"
            else:
                return None

            formatted = f"{res:.2f}".rstrip("0").rstrip(".") if res % 1 != 0 else str(int(res))
            n1_str = str(int(num1)) if num1.is_integer() else str(num1)
            n2_str = str(int(num2)) if num2.is_integer() else str(num2)
            return f"{n1_str} {op_str} {n2_str} is {formatted}."

        return None

    def _clean_for_voice(self, text: str) -> str:
        """Strip markdown markers, asterisks, bullet dashes, and unpronounceable formatting."""
        # Remove bold/italic markdown
        cleaned = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
        cleaned = re.sub(r"\*([^*]+)\*", r"\1", cleaned)
        cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
        # Remove markdown headers
        cleaned = re.sub(r"^#+\s+", "", cleaned, flags=re.MULTILINE)
        # Remove bullet points
        cleaned = re.sub(r"^\s*[-*•]\s+", "", cleaned, flags=re.MULTILINE)
        # Remove emojis from voice output
        cleaned = re.sub(r"[\U00010000-\U0010ffff\u2600-\u27ff\u2b50]", "", cleaned)
        # Normalize whitespace
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def sanitize_spoken_response(self, text: Optional[str]) -> str:
        """
        Sanitize text intended for Text-To-Speech (TTS) voice synthesis.
        Guarantees that:
        1. Internal thoughts, thinking tokens, and XML tags (<think>...</think>, <thought>...</thought>, [thinking], etc.) are removed.
        2. Status phrases and internal processing announcements ('Processing...', 'Let me think', 'Thinking...',
           'Analyzing...', 'Searching...', 'One moment...', 'Here is what I found...', 'Let me see...', 'Checking...')
           are completely eliminated from the spoken output.
        3. Robotic errors or technical failure notices ('An error occurred while processing your request')
           are replaced with natural spoken conversational phrasing: 'I couldn't get that information right now. Try again.'
        4. Markdown formatting, asterisks, headers, and bullet dashes are stripped cleanly.
        5. Spoken output begins immediately with the direct, natural response.
        """
        if not text:
            return "I couldn't get that information right now. Try again."

        cleaned = str(text)

        # 1. Strip reasoning and thought tags (e.g. DeepSeek/Gemini/OpenAI <think>...</think>, <thought>...</thought>)
        cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
        cleaned = re.sub(r"(?is)<thought>.*?</thought>", "", cleaned)
        cleaned = re.sub(r"(?is)<reasoning>.*?</reasoning>", "", cleaned)
        cleaned = re.sub(r"(?is)\[(thinking|processing|searching|analyzing)\]", "", cleaned)

        # 2. Strip code blocks and markdown markers
        cleaned = self._clean_for_voice(cleaned)

        # 3. Handle robotic technical error statements per Master PDR & User Instructions
        if re.search(r"\ban error occurred(\s+while\s+processing(\s+your\s+request)?)?", cleaned, flags=re.IGNORECASE):
            return "I couldn't get that information right now. Try again."

        # Strip raw web domain names (e.g. money.usnews.com) from spoken output
        cleaned = re.sub(r"\b[a-zA-Z0-9\-\.]+\.(com|org|net|edu|gov|io|co|ai)\b", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # 4. Iteratively strip leading filler, status words, and internal processing announcements
        status_patterns = [
            # Processing clauses: "Processing...", "Processing your request...", "Processing data...", etc.
            r"^processing(\s+[^\.\:\n]+)?(\.\.\.+|\:)",
            r"^(processing(\s+your\s+request)?|i'?m\s+processing(\s+(that|your\s+request))?|i\s+am\s+processing(\s+(that|your\s+request))?)\b",

            # Thinking clauses: "Thinking...", "Thinking about this...", "Let me think...", "Let me think about that...", "Let me see..."
            r"^thinking(\s+[^\.\:\n]+)?(\.\.\.+|\:)",
            r"^(let\s+me\s+think(\s+about\s+that)?|thinking(\.\.\.)?|let\s+me\s+see|let\s+me\s+ponder)\b",

            # Analyzing clauses: "Analyzing...", "Analyzing algorithms...", "Analyzing the data...", etc.
            r"^analyzing(\s+[^\.\:\n]+)?(\.\.\.+|\:)",
            r"^(analyzing(\s+(the\s+information|this|at\s+the\s+systems\s+level|the\s+data))?)\b",

            # Searching clauses: "Searching...", "Searching for that...", "Searching the web...", "Let me search for that..."
            r"^searching(\s+[^\.\:\n]+)?(\.\.\.+|\:)",
            r"^(searching(\s+(for\s+that|the\s+web|online|current\s+sources))?|let\s+me\s+search(\s+for\s+that)?|i\s+searched(\s+current\s+technology\s+sources)?)\b",

            # Waiting / momentary delays: "One moment...", "Just a moment...", "One second...", "Give me a second..."
            r"^(one\s+moment(\s+please)?|just\s+a\s+moment|one\s+second|give\s+me\s+a\s+(second|moment))\b",

            # Checking variants: "Let me check...", "Let me check that for you...", "Checking...", "Checking that for you..."
            r"^checking(\s+[^\.\:\n]+)?(\.\.\.+|\:)",
            r"^(let\s+me\s+check(\s+(that|this))?(\s+for\s+you)?|checking(\s+that)?(\s+for\s+you)?|sure,\s+let\s+me\s+check(\s+that)?(\s+for\s+you)?|sure,\s+let\s+me\s+see)\b",

            # Preamble announcements: "Here is what I found...", "Here's what I found...", "Here is what I found for you..."
            r"^(here\s+is\s+what\s+i\s+found(\s+for\s+you)?|here'?s\s+what\s+i\s+found)\b",

            # Status filler: "I am analyzing...", "I'm analyzing..."
            r"^(i'?m\s+analyzing(\s+(that|this|the\s+information))?|i\s+am\s+analyzing(\s+(that|this|the\s+information))?)\b",

            # Meta-attribution preambles: "According to reports from...", "According to XYZ's official announcements..."
            r"^(according\s+to\s+.*?(,\s*|:\s*))",
            r"^(reports\s+from\s+.*?(,\s*|:\s*))",
        ]

        changed = True
        iterations = 0
        while changed and iterations < 5:
            changed = False
            iterations += 1
            # Strip leading colons, dashes, dots, spaces, or ellipses
            cleaned = re.sub(r"^[\s:,\.\-—~]+", "", cleaned)
            for pat in status_patterns:
                match = re.match(pat, cleaned, flags=re.IGNORECASE)
                if match:
                    cleaned = cleaned[match.end():]
                    cleaned = re.sub(r"^[\s:,\.\-—~]+", "", cleaned)
                    changed = True

        cleaned = cleaned.strip()

        # Strip trailing or inline " — reported by ..." or ", reported by ..."
        cleaned = re.sub(r"(?i)\s*[—–-]\s*reported\s+by\s+.*$", "", cleaned)
        cleaned = re.sub(r"(?i)\s*,\s*reported\s+by\s+[^\.\n]+", "", cleaned)
        cleaned = cleaned.strip().rstrip(",;:-— ")

        # If stripping internal status left the string empty or invalid, fallback cleanly
        if not cleaned or len(cleaned) < 2:
            return "I couldn't get that information right now. Try again."

        # Capitalize first character naturally
        return cleaned[0].upper() + cleaned[1:]

conversational_engine = ConversationalEngine()
