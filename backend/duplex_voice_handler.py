"""
Razorpay Payment Recovery Engine — Full-Duplex Real-Time Voice Handler
Manages bi-directional WebSocket audio streaming, real-time STT via Groq Whisper,
LLM reasoning via Groq, and TTS voice synthesis.
"""

import asyncio
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import WebSocket
from groq import Groq

from voice_service import VoiceLLMCallingEngine

logger = logging.getLogger("DuplexVoiceHandler")

env_path = Path("d:/Machine Learning/.env")
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()


def transcribe_user_audio(audio_bytes: bytes, filename: str = "user_speech.webm", client: Optional[Groq] = None) -> str:
    """Transcribe mic audio with Groq Whisper. Language is auto-detected (English/Hindi/Hinglish)."""
    groq_client = client or (Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None)
    if not groq_client or not audio_bytes or len(audio_bytes) < 80:
        return ""

    name = (filename or "user_speech.webm").lower()
    if name.endswith(".wav"):
        mime = "audio/wav"
    elif name.endswith(".mp3"):
        mime = "audio/mpeg"
    elif name.endswith(".ogg"):
        mime = "audio/ogg"
    else:
        mime = "audio/webm"
        if not name.endswith(".webm"):
            name = "user_speech.webm"

    try:
        last_error = None
        for model in ("whisper-large-v3-turbo", "whisper-large-v3"):
            try:
                transcription = groq_client.audio.transcriptions.create(
                    file=(name, audio_bytes, mime),
                    model=model,
                    temperature=0.0,
                )
                text = (transcription.text or "").strip()
                if text:
                    return text
            except Exception as e:
                last_error = e
                logger.error("Groq Whisper STT Error (%s): %s", model, e)
        if last_error:
            logger.error("Groq Whisper STT failed after retries: %s", last_error)
        return ""
    except Exception as e:
        logger.error("Groq Whisper STT Error: %s", e)
        return ""


class DuplexVoiceSession:
    """Manages a live full-duplex voice call session over WebSocket."""

    def __init__(self, websocket: WebSocket, event_id: str, voice_agent_id: str = "swara_hi"):
        self.websocket = websocket
        self.event_id = event_id
        self.voice_agent_id = voice_agent_id
        self.engine = VoiceLLMCallingEngine()
        self.groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
        self.is_agent_speaking = False
        self.is_active = True

    async def initialize_call(self, event_data: Dict[str, Any]):
        call_start = self.engine.start_call(event_data, voice_agent_id=self.voice_agent_id)
        await self.websocket.send_json({
            "type": "AGENT_OPENING",
            "event_id": self.event_id,
            "agent_name": call_start.get("agent_name", "Agent"),
            "text": call_start.get("agent_opening_text", ""),
            "audio_base64": call_start.get("audio_base64", ""),
            "provider": call_start.get("audio_provider", ""),
        })
        self.is_agent_speaking = True

    def transcribe_audio_bytes(self, audio_bytes: bytes, filename: str = "user_speech.webm") -> str:
        return transcribe_user_audio(audio_bytes, filename, client=self.groq_client)

    async def handle_user_text_utterance(self, text: str):
        if not text or not text.strip():
            return

        logger.info("User Spoke: %s", text)

        if self.is_agent_speaking:
            await self.websocket.send_json({"type": "INTERRUPT_AGENT"})
            self.is_agent_speaking = False

        await self.websocket.send_json({"type": "USER_TRANSCRIPT", "text": text})

        turn_res = self.engine.process_turn(self.event_id, text, voice_agent_id=self.voice_agent_id)
        self.is_agent_speaking = True
        await self.websocket.send_json({
            "type": "AGENT_RESPONSE",
            "agent_name": turn_res.get("agent_name", "Agent"),
            "text": turn_res.get("agent_reply_text", ""),
            "audio_base64": turn_res.get("audio_base64", ""),
            "provider": turn_res.get("audio_provider", ""),
            "turn_count": turn_res.get("turn_count", 1),
        })

    async def handle_user_audio_chunk(self, audio_bytes: bytes):
        loop = asyncio.get_event_loop()
        transcribed_text = await loop.run_in_executor(None, self.transcribe_audio_bytes, audio_bytes)
        if transcribed_text:
            await self.handle_user_text_utterance(transcribed_text)
