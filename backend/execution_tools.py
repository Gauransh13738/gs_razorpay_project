"""
Execution Tools for Payment Recovery Interventions
Includes templated nudges (WhatsApp/SMS/Email), Mock Razorpay Payment Retry Stub, 
and Voice Agent Payload Generator (Retell AI / ElevenLabs integration).
"""

from typing import Dict, Any
import random
import json
import os

class ExecutionTools:
    
    @staticmethod
    def execute_nudge(event_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 4.1: Low-cost digital nudge generator (WhatsApp / SMS / Email)"""
        channel = event_state.get("channel_selected", "whatsapp")
        lang = event_state.get("language_pref", "hinglish")
        name = event_state.get("customer_name", "Customer")
        amount = event_state.get("amount_inr", 0.0)
        sub_reason = event_state.get("sub_reason", "payment_failure")
        evt_id = event_state.get("event_id", "000")
        
        pay_link = f"https://rzp.io/l/rec_{evt_id[:6]}"
        
        # Multilingual Templated Nudges
        templates = {
            "card_expired": {
                "hinglish": f"Hi {name}, aapka subscription payment expiry ki wajah se pause ho gaya hai. Simply update your card details here to keep services active: {pay_link}",
                "hindi": f"नमस्ते {name}, कार्ड एक्सपायर होने के कारण आपका भुगतान असफल रहा। सेवाओं को जारी रखने के लिए कार्ड विवरण अपडेट करें: {pay_link}",
                "english": f"Hi {name}, your subscription renewal failed due to an expired card. Update your card details in 30 secs to avoid service interruption: {pay_link}"
            },
            "insufficient_funds": {
                "hinglish": f"Hi {name}, aapka ₹{amount:,.2f} ka payment attempt clear nahi ho paya. Click here to retry via UPI or Card: {pay_link}",
                "hindi": f"नमस्ते {name}, आपका ₹{amount:,.2f} का भुगतान पूरा नहीं हो सका। कृपया यूपीआई या कार्ड से पुनः प्रयास करें: {pay_link}",
                "english": f"Hi {name}, your payment of ₹{amount:,.2f} could not be processed. Retry instantly using your preferred payment mode: {pay_link}"
            },
            "otp_abandon": {
                "hinglish": f"Hi {name}, aapka checkout incomplete tha (₹{amount:,.2f}). Don't worry, aapka cart saved hai! Complete payment in 1-click: {pay_link}",
                "hindi": f"नमस्ते {name}, आपका चेकआउट अधूरा रह गया था। इसे तुरंत पूरा करने के लिए यहाँ क्लिक करें: {pay_link}",
                "english": f"Hi {name}, you left your payment unfinished. Click here to complete your transaction securely: {pay_link}"
            },
            "cash_flow_delay": {
                "hinglish": f"Dear {name}, Invoice #{evt_id[:8]} for ₹{amount:,.2f} is due. Download invoice & complete payment via corporate UPI/NEFT: {pay_link}",
                "hindi": f"प्रिय {name}, आपका ₹{amount:,.2f} का चालान लंबित है। तुरंत भुगतान करने के लिए क्लिक करें: {pay_link}",
                "english": f"Dear {name}, Invoice #{evt_id[:8]} of ₹{amount:,.2f} remains pending. View invoice and execute payment here: {pay_link}"
            }
        }
        
        sub_templates = templates.get(sub_reason, templates["insufficient_funds"])
        msg_text = sub_templates.get(lang, sub_templates["hinglish"])
        
        cost_per_msg = {"whatsapp": 0.50, "sms": 0.15, "email": 0.05}
        
        return {
            "status": "SENT",
            "channel": channel,
            "recipient_name": name,
            "language": lang,
            "message_body": msg_text,
            "payment_link": pay_link,
            "estimated_cost_inr": cost_per_msg.get(channel, 0.20)
        }

    @staticmethod
    def execute_payment_retry(event_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 4.2: Payment Retry Stub (Mock Razorpay Gateway API call)"""
        evt_id = event_state.get("event_id")
        amount = event_state.get("amount_inr")
        
        # Mock gateway retry response simulation
        # Auto retries have a ~65% probability of succeeding on transient errors
        success = random.random() < 0.65
        
        return {
            "status": "GATEWAY_RETRY_EXECUTED",
            "api_endpoint": "POST /v1/payments/retry",
            "request_payload": {
                "event_id": evt_id,
                "amount": amount,
                "retry_mode": "auto_background_debit"
            },
            "response": {
                "status_code": 200 if success else 400,
                "gateway_status": "captured" if success else "failed",
                "reason": "Payment captured successfully" if success else "Issuer bank still unresponsive"
            },
            "estimated_cost_inr": 0.00
        }

    @staticmethod
    def generate_voice_agent_payload(event_state: Dict[str, Any]) -> Dict[str, Any]:
        """Step 4.3: Voice Call Payload (Groq LLM Brain + ElevenLabs TTS Config)"""
        name = event_state.get("customer_name", "Customer")
        amount = event_state.get("amount_inr", 0.0)
        sub_reason = event_state.get("sub_reason", "payment_failure")
        lang = event_state.get("language_pref", "hinglish")
        evt_id = event_state.get("event_id", "000")
        pay_link = f"https://rzp.io/l/rec_{evt_id[:6]}"
        
        opening_lines = {
            "hinglish": f"Namaste {name} ji, main Razorpay Payment Support se Riya bol rahi hoon. Aapka Rs. {amount:,.2f} ka payment attempt clear nahi ho paya. Kya main aapki help kar sakti hoon?",
            "hindi": f"Namaste {name} ji, main Razorpay Payment Support se Riya bol rahi hoon. Aapka Rs. {amount:,.2f} ka bhugtan poora nahi ho saka.",
            "english": f"Hello {name}, this is Riya calling from Razorpay Payment Support regarding your transaction of Rs. {amount:,.2f}."
        }
        
        opening = opening_lines.get(lang, opening_lines["hinglish"])
        
        return {
            "status": "LIVE_CALL_SCHEDULED",
            "provider": "ElevenLabs_Groq_Engine",
            "agent_id": "agent_rzp_recovery_v1",
            "call_config": {
                "voice_id": os.getenv("VOICE_ID", "r1KmysJdVYZjJCm4mL3b"),
                "language": lang,
                "agent_opening_line": opening,
                "payment_link": pay_link,
                "objection_strategy": f"Dynamic Groq LLM + ElevenLabs TTS voice resolution for {sub_reason}."
            },
            "estimated_cost_inr": 3.50
        }

if __name__ == "__main__":
    print("Testing Execution Tools...")
    sample_state = {
        "event_id": "evt_abc123",
        "customer_name": "Rohan Nair",
        "amount_inr": 4500.0,
        "contact_channel_pref": "whatsapp",
        "language_pref": "hinglish",
        "sub_reason": "insufficient_funds",
        "channel_selected": "whatsapp"
    }
    
    nudge_res = ExecutionTools.execute_nudge(sample_state)
    print("\n--- NUDGE RESULT ---")
    print(json.dumps(nudge_res, indent=2))
    
    voice_res = ExecutionTools.generate_voice_agent_payload(sample_state)
    print("\n--- VOICE AGENT PAYLOAD ---")
    print(json.dumps(voice_res, indent=2))
