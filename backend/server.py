"""
Razorpay Payment Recovery Engine — Full-Duplex Real-Time Voice Server (FastAPI)
Exposes REST APIs and bi-directional WebSocket endpoints (/ws/call/{event_id})
for real-time microphone duplex speech conversations with voice agents.
"""

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import pandas as pd
import json
import os
import logging
from typing import Optional
from pathlib import Path
from voice_service import VoiceLLMCallingEngine, VOICE_AGENTS
from duplex_voice_handler import DuplexVoiceSession, transcribe_user_audio
from payment_workflow import (
    compute_metrics,
    load_events_df,
    mark_event_recovered,
    simulate_checkout,
    TEST_CARDS,
)

BASE_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("DuplexServer")

app = FastAPI(title="Razorpay Duplex Real-Time Voice Engine")

# CORS Configuration - Update with your Render frontend URL for production
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://gs-razorpay-project-backend.onrender.com")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        FRONTEND_URL,
        "http://localhost:3000",  # Local development
        "http://localhost:8000",  # Local development
        "*",  # Allow all origins for development (remove in production)
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = VoiceLLMCallingEngine()

class StartCallRequest(BaseModel):
    event_id: str
    voice_agent_id: str = "swara_hi"
    customer_name: Optional[str] = None
    amount_inr: Optional[float] = None
    sub_reason: Optional[str] = None
    language_pref: Optional[str] = None
    reset_session: bool = True

class RespondCallRequest(BaseModel):
    event_id: str
    customer_utterance: str
    voice_agent_id: str = "swara_hi"

# load_events_df imported from payment_workflow

def get_event_by_id(event_id: str) -> dict:
    df = load_events_df()
    if not df.empty:
        matches = df[df["event_id"] == event_id]
        if not matches.empty:
            item = matches.iloc[0].to_dict()
            item["amount_inr"] = float(item.get("amount_inr", 5000.0))
            return item
    return {
        "event_id": event_id,
        "customer_name": "Valued Customer",
        "amount_inr": 5000.0,
        "sub_reason": "payment_failure",
        "language_pref": "hinglish",
        "contact_channel_pref": "voice"
    }

@app.get("/api/events")
def get_events():
    df = load_events_df()
    if df.empty:
        return {"events": []}
    # NaN/inf in CSV cells are not JSON-compliant
    records = json.loads(df.to_json(orient="records"))
    return {"events": records}

@app.get("/api/voice/agents")
def get_voice_agents():
    return {"agents": VOICE_AGENTS}

@app.post("/api/voice/call")
def initiate_voice_call(req: StartCallRequest):
    event_dict = get_event_by_id(req.event_id)
    # Dynamically override with request payload if provided
    if req.customer_name:
        event_dict["customer_name"] = req.customer_name
    if req.amount_inr is not None:
        event_dict["amount_inr"] = float(req.amount_inr)
    if req.sub_reason:
        event_dict["sub_reason"] = req.sub_reason
    if req.language_pref:
        event_dict["language_pref"] = req.language_pref

    if req.reset_session:
        engine.reset_session(req.event_id, req.voice_agent_id)
    call_result = engine.start_call(event_dict, voice_agent_id=req.voice_agent_id)
    return call_result

@app.post("/api/voice/transcribe")
async def transcribe_voice_audio(audio: UploadFile = File(...)):
    payload = await audio.read()
    text = transcribe_user_audio(payload, audio.filename or "user_speech.webm")
    if not text:
        return {"text": "", "status": "EMPTY"}
    return {"text": text, "status": "OK"}

@app.post("/api/voice/respond")
def continue_voice_call(req: RespondCallRequest):
    if not req.event_id or not req.customer_utterance:
        raise HTTPException(status_code=400, detail="event_id and customer_utterance are required")
    turn_result = engine.process_turn(req.event_id, req.customer_utterance, voice_agent_id=req.voice_agent_id)
    return turn_result

# ==============================================================================
# FULL-DUPLEX REAL-TIME WEBSOCKET ENDPOINT
# ==============================================================================
@app.websocket("/ws/call/{event_id}")
async def websocket_duplex_voice_call(websocket: WebSocket, event_id: str):
    """
    Bi-directional full-duplex WebSocket connection for real-time microphone voice chat.
    Sends agent speech audio streams and receives live user speech audio / text turns.
    """
    await websocket.accept()
    logger.info(f"WebSocket Duplex Call Connected for event: {event_id}")
    
    session = None
    try:
        # 1. Wait for initial setup message
        init_data = await websocket.receive_text()
        init_json = json.loads(init_data)
        
        voice_agent_id = init_json.get("voice_agent_id", "swara_hi")
        event_dict = get_event_by_id(event_id)
        
        session = DuplexVoiceSession(websocket, event_id, voice_agent_id=voice_agent_id)
        await session.initialize_call(event_dict)
        
        # 2. Main Duplex Event Loop
        while True:
            message = await websocket.receive()
            
            if "text" in message and message["text"]:
                msg_text = message["text"]
                try:
                    payload = json.loads(msg_text)
                    msg_type = payload.get("type")
                    
                    if msg_type == "USER_UTTERANCE":
                        user_text = payload.get("text", "")
                        await session.handle_user_text_utterance(user_text)
                    elif msg_type == "INTERRUPT":
                        session.is_agent_speaking = False
                    elif msg_type == "END_CALL":
                        break
                except json.JSONDecodeError:
                    # Treat raw text string as user utterance
                    await session.handle_user_text_utterance(msg_text)
                    
            elif "bytes" in message and message["bytes"]:
                # Incoming raw microphone audio chunk
                audio_bytes = message["bytes"]
                await session.handle_user_audio_chunk(audio_bytes)
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket Duplex Call Disconnected for event: {event_id}")
    except Exception as e:
        logger.error(f"WebSocket Exception: {e}")
    finally:
        logger.info(f"Cleaned up session for event: {event_id}")

# ==============================================================================
# RAZORPAY PAYMENT INTEGRATION & WEBHOOK ENDPOINTS
# ==============================================================================
from razorpay_integration import razorpay_manager

class CreatePaymentLinkRequest(BaseModel):
    event_id: str

class WebhookCapturedRequest(BaseModel):
    event_id: str
    payment_method: str = "upi"

@app.post("/api/razorpay/create_link")
def create_razorpay_payment_link(req: CreatePaymentLinkRequest):
    event_dict = get_event_by_id(req.event_id)
    name = event_dict.get("customer_name", "Valued Customer")
    amount = float(event_dict.get("amount_inr", 5000.0))
    sub_reason = event_dict.get("sub_reason", "payment_degradation")
    
    link_data = razorpay_manager.create_payment_link(req.event_id, name, amount, sub_reason)
    return link_data

@app.post("/api/razorpay/webhook")
def process_razorpay_webhook(req: WebhookCapturedRequest):
    record = razorpay_manager.handle_webhook_payment_captured(req.event_id, req.payment_method)
    mark_event_recovered(req.event_id)
    return {"status": "SUCCESS", "message": "Payment captured webhook processed.", "recovery": record}

class SimulatePaymentRequest(BaseModel):
    card_number: str
    cvv: str = "123"
    expiry: str = "12/29"
    amount_inr: float = 5000.0
    customer_name: str = "Test Customer"
    city: str = "Mumbai"
    contact_channel_pref: str = "voice"
    language_pref: str = "hinglish"
    bank_action: str = "success"
    failure_reason: Optional[str] = None

@app.post("/api/payments/simulate")
def api_simulate_payment(req: SimulatePaymentRequest):
    result = simulate_checkout(
        card_number=req.card_number,
        cvv=req.cvv,
        expiry=req.expiry,
        amount_inr=req.amount_inr,
        customer_name=req.customer_name,
        city=req.city,
        contact_channel_pref=req.contact_channel_pref,
        language_pref=req.language_pref,
        bank_action=req.bank_action,
        failure_reason=req.failure_reason,
        voice_engine=engine,
    )
    return result

@app.get("/api/payments/test-cards")
def api_test_cards():
    cards = []
    for pan, meta in TEST_CARDS.items():
        spaced = " ".join(pan[i:i + 4] for i in range(0, len(pan), 4))
        cards.append({"pan": pan, "display": spaced, **meta})
    return {"source": "https://razorpay.com/docs/payments/payments/test-card-details/", "cards": cards}

@app.get("/api/metrics")
def api_metrics():
    return compute_metrics()

@app.get("/api/audit/logs")
def get_audit_logs():
    audit_file = BASE_DIR / "audit_trail.json"
    if audit_file.exists():
        try:
            with open(audit_file, "r", encoding="utf-8") as f:
                logs = json.load(f)
                return {"logs": logs}
        except Exception:
            pass
    return {"logs": []}

@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    dash_path = BASE_DIR.parent / "frontend" / "dashboard.html"
    if dash_path.exists():
        content = dash_path.read_text(encoding="utf-8")
        return HTMLResponse(
            content=content,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate",
                "Pragma": "no-cache",
            }
        )
    return "<h1>Razorpay Payment Recovery Engine - Dashboard file missing.</h1>"

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    except Exception:
        uvicorn.run(app, host="0.0.0.0", port=8080)
