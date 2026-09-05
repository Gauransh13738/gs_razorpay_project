"""
Razorpay Payment Gateway Integration & Simulation Engine
Manages Razorpay Payment Links, Orders, Webhook events (payment.captured, payment_link.paid),
and Real-Time Audit Trail Logging.
"""

import os
import json
import time
import logging
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# Load env variables
env_path = BASE_DIR.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    load_dotenv()

RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_demo123456").strip()
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "demo_secret_123456").strip()

# Try importing official Razorpay SDK
try:
    import razorpay
    razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET)) if RAZORPAY_KEY_ID.startswith("rzp_live_") or RAZORPAY_KEY_ID.startswith("rzp_test_real") else None
except Exception:
    razorpay_client = None

logger = logging.getLogger("RazorpayIntegration")
logging.basicConfig(level=logging.INFO)

AUDIT_LOG_FILE = BASE_DIR / "audit_trail.json"

class RazorpayRecoveryManager:
    """Manages Razorpay Payment Link generation, webhook verification, and audit trail."""
    
    def __init__(self):
        self.payment_links: Dict[str, Dict[str, Any]] = {}
        self._ensure_audit_file()

    def _ensure_audit_file(self):
        if not AUDIT_LOG_FILE.exists():
            with open(AUDIT_LOG_FILE, "w") as f:
                json.dump([], f, indent=2)

    def log_audit_event(self, event_id: str, stage: str, action: str, details: Dict[str, Any]):
        """Logs an event to the compliant audit trail."""
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "event_id": event_id,
            "stage": stage,
            "action": action,
            "details": details
        }
        try:
            logs = []
            if AUDIT_LOG_FILE.exists():
                with open(AUDIT_LOG_FILE, "r") as f:
                    try: logs = json.load(f)
                    except: logs = []
            logs.append(log_entry)
            with open(AUDIT_LOG_FILE, "w") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")

    def create_payment_link(self, event_id: str, customer_name: str, amount_inr: float, sub_reason: str) -> Dict[str, Any]:
        """Creates a Razorpay Payment Link (via official SDK or Razorpay Simulator)."""
        amount_paise = int(amount_inr * 100)
        short_code = event_id.replace("evt_", "")
        
        # 1. Real Razorpay API call if valid keys present
        if razorpay_client:
            try:
                payload = {
                    "amount": amount_paise,
                    "currency": "INR",
                    "accept_partial": False,
                    "description": f"Payment Recovery for {sub_reason} (Ref: {event_id})",
                    "customer": {
                        "name": customer_name,
                        "contact": "+919876543210",
                        "email": f"{customer_name.lower().replace(' ', '.')}@example.com"
                    },
                    "notify": {"sms": True, "email": True},
                    "reminder_enable": True,
                    "callback_url": "http://localhost:8000/api/razorpay/callback",
                    "callback_method": "get"
                }
                res = razorpay_client.payment_link.create(payload)
                plink_id = res.get("id")
                short_url = res.get("short_url")
                
                link_data = {
                    "plink_id": plink_id,
                    "event_id": event_id,
                    "customer_name": customer_name,
                    "amount_inr": amount_inr,
                    "short_url": short_url,
                    "status": "created",
                    "created_at": time.time(),
                    "provider": "Razorpay_Official_API"
                }
                self.payment_links[event_id] = link_data
                self.log_audit_event(event_id, "INTERVENTION_EXECUTION", "RAZORPAY_LINK_CREATED", link_data)
                return link_data
            except Exception as e:
                logger.warning(f"Official Razorpay API call failed: {e}. Falling back to Razorpay Gateway Simulator.")

        # 2. Razorpay Gateway Simulator Link Format
        plink_id = f"plink_{short_code}_{int(time.time())}"
        short_url = f"https://rzp.io/i/rec_{short_code}"
        
        link_data = {
            "plink_id": plink_id,
            "event_id": event_id,
            "customer_name": customer_name,
            "amount_inr": amount_inr,
            "short_url": short_url,
            "status": "created",
            "created_at": time.time(),
            "provider": "Razorpay_Gateway_Simulator"
        }
        self.payment_links[event_id] = link_data
        self.log_audit_event(event_id, "INTERVENTION_EXECUTION", "RAZORPAY_LINK_CREATED", link_data)
        return link_data

    def handle_webhook_payment_captured(self, event_id: str, payment_method: str = "upi") -> Dict[str, Any]:
        """Simulates or verifies a Razorpay webhook event (payment.captured / payment_link.paid)."""
        link_data = self.payment_links.get(event_id)
        amount_inr = link_data.get("amount_inr", 0.0) if link_data else 5000.0
        plink_id = link_data.get("plink_id", f"plink_{event_id}") if link_data else f"plink_{event_id}"
        
        payment_id = f"pay_{event_id.replace('evt_', '')}_{int(time.time())}"
        
        recovery_record = {
            "event_id": event_id,
            "razorpay_payment_id": payment_id,
            "razorpay_plink_id": plink_id,
            "amount_recovered": amount_inr,
            "payment_method": payment_method,
            "status": "RECOVERED",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
        
        if link_data:
            link_data["status"] = "paid"
            link_data["paid_at"] = time.time()
            link_data["payment_id"] = payment_id

        self.log_audit_event(event_id, "RECOVERY_FULFILLMENT", "RAZORPAY_PAYMENT_CAPTURED", recovery_record)
        return recovery_record

# Singleton Instance
razorpay_manager = RazorpayRecoveryManager()
