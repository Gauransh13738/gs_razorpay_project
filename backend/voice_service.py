"""
Razorpay Payment Recovery Engine — Voice LLM Calling Service
Supports multiple voice agents (ElevenLabs, Edge-TTS Neural Swara/Madhur/Neerja/Prabhat, gTTS)
with Groq LLM ('qwen/qwen3.8-27b') Conversational Agent Brain.
"""

import os
import re
import json
import time
import base64
import asyncio
import requests
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq

# Configure Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("VoiceLLMService")

# Load environment variables
env_path = Path("d:/Machine Learning/.env")
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
VOICE_ID = os.getenv("VOICE_ID", "r1KmysJdVYZjJCm4mL3b").strip()

GROQ_MODEL = "qwen/qwen3.8-27b"

AUDIO_DIR = Path("d:/Machine Learning/razorpay_proj/voice_calls")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Voice Agent Profiles Map (Simplified 2 Rock-Solid Agents)
VOICE_AGENTS = {
    "swara_hi": {
        "name": "Swara",
        "gender": "Female",
        "language": "Hindi / Hinglish",
        "edge_voice": "hi-IN-SwaraNeural",
        "description": "Empathetic Hindi & Hinglish Specialist Agent"
    },
    "ava_us": {
        "name": "Ava",
        "gender": "Female",
        "language": "Pure English",
        "edge_voice": "en-US-JennyNeural",
        "description": "Warm & conversational native US English specialist (Jenny Neural)"
    }
}

class VoiceAudioSynthesizer:
    """Voice Audio Synthesizer (EdgeTTS Neural hi-IN-SwaraNeural & en-US-AvaNeural -> gTTS fallback)"""
    
    def __init__(self, voice_agent_id: str = "swara_hi"):
        self.voice_agent_id = voice_agent_id if voice_agent_id in VOICE_AGENTS else "swara_hi"
        self.agent_profile = VOICE_AGENTS[self.voice_agent_id]
        
    def generate_speech(self, text: str, output_path: Optional[Path] = None) -> Dict[str, Any]:
        """Synthesizes text into audio using selected voice agent."""
        if not text:
            return {"status": "ERROR", "message": "Text cannot be empty."}
            
        edge_voice_name = self.agent_profile.get("edge_voice", "hi-IN-SwaraNeural")
        try:
            return self._call_edge_tts(text, edge_voice_name, output_path)
        except Exception as e:
            logger.warning(f"EdgeTTS failed: {e}. Falling back to gTTS...")
            return self._call_gtts(text, output_path)

    def _call_elevenlabs(self, text: str, output_path: Optional[Path] = None) -> Dict[str, Any]:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}"
        headers = {
            "xi-api-key": ELEVENLABS_API_KEY,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg"
        }
        payload = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {"stability": 0.50, "similarity_boost": 0.75}
        }
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=12)
            if r.status_code == 200:
                if output_path:
                    with open(output_path, "wb") as f:
                        f.write(r.content)
                return {
                    "status": "SUCCESS",
                    "provider": "ElevenLabs_API",
                    "audio_base64": base64.b64encode(r.content).decode("utf-8"),
                    "audio_path": str(output_path) if output_path else None
                }
        except Exception as e:
            logger.error(f"ElevenLabs error: {e}")
        return {"status": "FAILED"}

    def _call_edge_tts(self, text: str, voice_name: str, output_path: Optional[Path] = None) -> Dict[str, Any]:
        import edge_tts
        if not output_path:
            output_path = AUDIO_DIR / "temp_edge_speech.mp3"
            
        async def run_edge():
            communicate = edge_tts.Communicate(text, voice_name)
            await communicate.save(str(output_path))
            
        asyncio.run(run_edge())
        
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
            
        return {
            "status": "SUCCESS",
            "provider": f"EdgeTTS_Neural ({self.agent_profile['name']})",
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "audio_path": str(output_path),
            "voice_agent": self.agent_profile["name"]
        }

    def _call_gtts(self, text: str, output_path: Optional[Path] = None) -> Dict[str, Any]:
        from gtts import gTTS
        if not output_path:
            output_path = AUDIO_DIR / "temp_gtts_speech.mp3"
        lang_code = "hi" if "swara" in self.voice_agent_id or "madhur" in self.voice_agent_id else "en"
        tts = gTTS(text=text, lang=lang_code)
        tts.save(str(output_path))
        with open(output_path, "rb") as f:
            audio_bytes = f.read()
        return {
            "status": "SUCCESS",
            "provider": "gTTS_Speech_Engine",
            "audio_base64": base64.b64encode(audio_bytes).decode("utf-8"),
            "audio_path": str(output_path)
        }


class VoiceAgentLLM:
    """Conversational AI Agent Brain powered by Groq LLM"""
    
    SYSTEM_PROMPT = """
You are {agent_name}, a senior Payment Resolution Specialist at Razorpay Payment Support.
Tone: Warm, professional, helpful, respectful, and persuasive.
Language Instruction: {language_instruction}
Customer Name: {customer_name}
Amount: ₹{amount_inr:,.2f}
Failure Reason: {sub_reason}

Direct payment resolution link: https://rzp.io/l/rec_{event_id_short}

Keep responses concise (2-3 sentences max) tailored for natural phone speech.
"""

    def __init__(self, api_key: str = None):
        self.api_key = api_key or GROQ_API_KEY
        self.groq_client = Groq(api_key=self.api_key) if self.api_key else None
        
    def _get_language_instruction(self, voice_agent_id: str, default_pref: str) -> str:
        if voice_agent_id in ["ava_us", "andrew_us"]:
            return "STRICT RULE: Speak ONLY in 100% Pure Natural English. Do NOT use ANY Hindi or Hinglish words under any circumstances (No 'Namaste', 'ji', 'aapka', 'hain', 'mein', 'dhanyavaad', etc.)."
        elif voice_agent_id in ["neerja_en", "prabhat_en"]:
            return "Speak in clear Indian English."
        return f"Language Preference: {default_pref}"

    def generate_opening(self, event: Dict[str, Any], agent_name: str = "Swara", voice_agent_id: str = "swara_hi") -> str:
        name = event.get("customer_name", "Customer")
        amount = event.get("amount_inr", 0.0)
        sub_reason = event.get("sub_reason", "")
        lang_pref = event.get("language_pref", "hinglish")
        lang_instruction = self._get_language_instruction(voice_agent_id, lang_pref)
        
        if self.groq_client:
            prompt = (
                f"This is a BRAND NEW phone call (agent switch / fresh session). "
                f"Write a unique 2-sentence opening as agent '{agent_name}' for {name} about a failed payment of ₹{amount:,.2f} due to {sub_reason}. "
                f"Do not reuse a previous greeting. Vary wording. Stay in character for {agent_name}."
            )
            sys_prompt = self.SYSTEM_PROMPT.format(
                agent_name=agent_name,
                language_instruction=lang_instruction,
                customer_name=name,
                amount_inr=amount,
                sub_reason=sub_reason,
                event_id_short=event.get("event_id", "000")[:6]
            )
            try:
                res = self.groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=[
                        {"role": "system", "content": sys_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    max_tokens=120,
                    temperature=0.7
                )
                return res.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq API Error: {e}")
                
        if voice_agent_id in ["ava_us", "andrew_us"]:
            return f"Hello {name}, this is {agent_name} from Razorpay Support. Your payment of ₹{amount:,.2f} failed due to {sub_reason}. Could I assist you with completing it right now?"
        return f"Namaste {name} ji, main Razorpay Payment Support se {agent_name} bol raha/rahi hoon. Aapka ₹{amount:,.2f} ka payment process nahi ho paya. Kya main aapki help karoon?"

    def generate_response(self, event: Dict[str, Any], conversation_history: List[Dict[str, str]], user_utterance: str, agent_name: str = "Swara", voice_agent_id: str = "swara_hi") -> str:
        lang_pref = event.get("language_pref", "hinglish")
        name = event.get("customer_name", "Customer")
        amount = event.get("amount_inr", 0.0)
        sub_reason = event.get("sub_reason", "")
        lang_instruction = self._get_language_instruction(voice_agent_id, lang_pref)
        
        if self.groq_client:
            sys_prompt = self.SYSTEM_PROMPT.format(
                agent_name=agent_name,
                language_instruction=lang_instruction,
                customer_name=name,
                amount_inr=amount,
                sub_reason=sub_reason,
                event_id_short=event.get("event_id", "000")[:6]
            )
            messages = [{"role": "system", "content": sys_prompt}]
            messages.extend(conversation_history)
            messages.append({"role": "user", "content": user_utterance})
            
            try:
                res = self.groq_client.chat.completions.create(
                    model=GROQ_MODEL,
                    messages=messages,
                    max_tokens=150,
                    temperature=0.6
                )
                return res.choices[0].message.content.strip()
            except Exception as e:
                logger.error(f"Groq Response Exception: {e}")
                
        if voice_agent_id in ["ava_us", "andrew_us"]:
            return f"I completely understand. I can send you an instant 1-click payment link right now so you can complete the transaction conveniently."
        return f"Samajh sakti hoon ji. Main aapko 1-click payment link bhej rahi hoon taaki aap aasaani se complete kar sakein."


class VoiceLLMCallingEngine:
    """Orchestrator combining Groq LLM Brain & Multi-Voice Audio Synthesizer"""
    
    def __init__(self):
        self.llm = VoiceAgentLLM()
        self.active_sessions: Dict[str, Dict[str, Any]] = {}

    def reset_session(self, evt_id: str, voice_agent_id: Optional[str] = None) -> None:
        """Drop stored history so the next call starts with a blank transcript."""
        self.active_sessions.pop(evt_id, None)
        if voice_agent_id:
            self.active_sessions.pop(f"{evt_id}::{voice_agent_id}", None)
        
    def start_call(self, event: Dict[str, Any], voice_agent_id: str = "swara_hi") -> Dict[str, Any]:
        evt_id = event.get("event_id", "evt_unknown")
        synthesizer = VoiceAudioSynthesizer(voice_agent_id=voice_agent_id)
        agent_name = synthesizer.agent_profile["name"]
        
        opening_text = self.llm.generate_opening(event, agent_name=agent_name, voice_agent_id=voice_agent_id)
        output_file = AUDIO_DIR / f"call_{evt_id}_opening.mp3"
        
        audio_res = synthesizer.generate_speech(opening_text, output_file)
        
        # Always create a completely fresh session — never carry over old history or event data
        self.active_sessions[evt_id] = {
            "event_id": evt_id,
            "voice_agent_id": voice_agent_id,
            "agent_name": agent_name,
            "event_data": event,  # Live event data from this specific call
            "history": [{"role": "assistant", "content": opening_text}],
            "turn_count": 1
        }
        
        return {
            "event_id": evt_id,
            "customer_name": event.get("customer_name"),
            "voice_agent_id": voice_agent_id,
            "agent_name": agent_name,
            "agent_opening_text": opening_text,
            "audio_base64": audio_res.get("audio_base64"),
            "audio_provider": audio_res.get("provider"),
            "status": "CALL_CONNECTED"
        }
        
    def process_turn(self, evt_id: str, customer_utterance: str, voice_agent_id: Optional[str] = None) -> Dict[str, Any]:
        session = self.active_sessions.get(evt_id)
        v_id = voice_agent_id or (session.get("voice_agent_id") if session else None) or "swara_hi"
        synthesizer = VoiceAudioSynthesizer(voice_agent_id=v_id)
        agent_name = synthesizer.agent_profile["name"]

        if not session or session.get("voice_agent_id") != v_id:
            session = {
                "event_id": evt_id,
                "voice_agent_id": v_id,
                "agent_name": agent_name,
                "event_data": (session or {}).get("event_data") or {
                    "event_id": evt_id,
                    "customer_name": "Customer",
                    "amount_inr": 5000.0,
                    "sub_reason": "insufficient_funds",
                    "language_pref": "english" if v_id == "ava_us" else "hinglish",
                },
                "history": [],
                "turn_count": 1
            }
            self.active_sessions[evt_id] = session
        
        event_data = session["event_data"]
        history = session["history"]
        
        agent_reply = self.llm.generate_response(event_data, history, customer_utterance, agent_name=agent_name, voice_agent_id=v_id)
        
        history.append({"role": "user", "content": customer_utterance})
        history.append({"role": "assistant", "content": agent_reply})
        session["turn_count"] += 1
        
        output_file = AUDIO_DIR / f"call_{evt_id}_turn_{session['turn_count']}.mp3"
        audio_res = synthesizer.generate_speech(agent_reply, output_file)
        
        return {
            "event_id": evt_id,
            "customer_utterance": customer_utterance,
            "agent_reply_text": agent_reply,
            "voice_agent_id": v_id,
            "agent_name": agent_name,
            "audio_base64": audio_res.get("audio_base64"),
            "audio_provider": audio_res.get("provider"),
            "turn_count": session["turn_count"]
        }

if __name__ == "__main__":
    print("Testing Multi-Voice Agent Engine...")
    engine = VoiceLLMCallingEngine()
    test_event = {"event_id": "evt_test_v2", "customer_name": "Rohan Nair", "amount_inr": 8500.0, "sub_reason": "card_expired", "language_pref": "hinglish"}
    
    res = engine.start_call(test_event, voice_agent_id="swara_hi")
    print(f"\nVoice Agent : {res['agent_name']} ({res['voice_agent_id']})")
    print(f"Opening     : {res['agent_opening_text'].encode('ascii', 'ignore').decode()}")
    print(f"Provider    : {res['audio_provider']}")
