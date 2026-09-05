"""
LangGraph Payment Triage & Intervention-Selection Engine
Handles payment failure classification, recoverability scoring, urgency assessment,
stopping rule enforcement, and intervention decisioning.
"""

from typing import TypedDict, Optional, Dict, Any, List
import pandas as pd
import json
from datetime import datetime
from langgraph.graph import StateGraph, END

# Define the State schema for LangGraph
class PaymentEventState(TypedDict):
    # Input event fields
    event_id: str
    customer_id: str
    customer_name: str
    city: str
    failure_type: str
    sub_reason: str
    amount_inr: float
    currency: str
    failed_at: str
    detected_at: str
    contact_channel_pref: str
    language_pref: str
    prior_attempts: int
    risk_score: float
    phone_masked: str
    do_not_disturb_hours: str
    
    # Node 1 Outputs: Classification & Scoring
    recoverability_score: float
    urgency: str  # CRITICAL, HIGH, MEDIUM, LOW
    failure_category: str
    is_recoverable: bool
    
    # Node 2 Outputs: Decision & Audit Trail
    action: str  # AUTO_RETRY | NUDGE_WHATSAPP | NUDGE_SMS | NUDGE_EMAIL | VOICE_CALL | ESCALATE_HUMAN | NO_ACTION_STOP
    channel_selected: str
    reason_string: str
    stopping_rule_triggered: Optional[str]
    recommended_delay_mins: int
    script_template_key: str

# Node 1: Classify Failure Node
def _s(val, default="") -> str:
    """Safely coerce any value (including NaN floats) to a stripped string."""
    if val is None:
        return default
    if isinstance(val, float) and val != val:  # NaN check
        return default
    return str(val).strip()

def classify_failure_node(state: PaymentEventState) -> Dict[str, Any]:
    sub_reason = _s(state.get("sub_reason")).lower()
    failure_type = _s(state.get("failure_type")).lower()
    amount = float(state.get("amount_inr") or 0.0)
    risk_score = float(state.get("risk_score") or 0.0)
    try:
        prior_attempts = int(state.get("prior_attempts") or 0)
    except (ValueError, TypeError):
        prior_attempts = 0
    
    # Base recoverability score matrix by sub_reason
    base_scores = {
        "insufficient_funds": 0.85,      # High recoverability after payday / nudge
        "card_expired": 0.80,            # High recoverability via quick link to update card
        "wrong_cvv_otp_fail": 0.75,      # High recoverability - user just needs nudge to re-enter OTP
        "otp_abandon": 0.70,             # Good recoverability via WhatsApp instant checkout link
        "payment_page_drop": 0.65,       # Moderate recoverability
        "bank_decline": 0.75,            # High recoverability via auto-retry or retry link
        "cash_flow_delay": 0.60,         # Moderate - B2B overdue payment
        "forgotten": 0.70,               # High - B2B simple reminder nudge
        "price_hesitation": 0.40,        # Lower - requires discount or voice objection handling
        "invoice_dispute": 0.35,         # Requires human escalation / voice call
        "genuine_abandonment": 0.15,     # Low recoverability
        "mandate_revoked": 0.05,         # User intentionally revoked mandate
    }
    
    recoverability = base_scores.get(sub_reason, 0.50)
    
    # Adjust for risk score and prior failed attempts
    recoverability -= (risk_score * 0.20)
    recoverability -= (prior_attempts * 0.15)
    recoverability = max(0.01, min(0.99, round(recoverability, 2)))
    
    # Assess Urgency based on Amount & Failure Type
    if failure_type == "overdue_invoice" or amount >= 50000:
        urgency = "CRITICAL" if amount >= 100000 else "HIGH"
    elif failure_type == "subscription_lapse":
        urgency = "HIGH" if sub_reason == "card_expired" else "MEDIUM"
    elif sub_reason in ["otp_abandon", "wrong_cvv_otp_fail"]:
        urgency = "HIGH"  # Immediate intervention while customer is still on phone/computer
    else:
        urgency = "LOW" if amount < 1000 else "MEDIUM"
        
    # Categorize failure profile
    if sub_reason in ["mandate_revoked", "genuine_abandonment"]:
        failure_category = "IRRECOVERABLE_OR_REVOKED"
    elif sub_reason == "bank_decline":
        failure_category = "TRANSIENT_BANK_ERROR"
    elif sub_reason in ["insufficient_funds", "card_expired"]:
        failure_category = "RECOVERABLE_PAYMENT_METHOD"
    elif sub_reason in ["otp_abandon", "payment_page_drop", "wrong_cvv_otp_fail"]:
        failure_category = "CHECKOUT_ABANDONED"
    elif failure_type == "overdue_invoice":
        failure_category = "B2B_INVOICE_PENDING"
    else:
        failure_category = "GENERAL_FAILURE"
        
    is_recoverable = recoverability >= 0.30 and failure_category != "IRRECOVERABLE_OR_REVOKED"
    
    return {
        "recoverability_score": recoverability,
        "urgency": urgency,
        "failure_category": failure_category,
        "is_recoverable": is_recoverable
    }

# Node 2: Decide Action Node (Intervention Selection & Stopping Rules)
def decide_action_node(state: PaymentEventState) -> Dict[str, Any]:
    try:
        prior_attempts = int(state.get("prior_attempts") or 0)
    except (ValueError, TypeError):
        prior_attempts = 0
    risk_score = float(state.get("risk_score") or 0.0)
    is_recoverable = state.get("is_recoverable", False)
    sub_reason = _s(state.get("sub_reason")).lower()
    failure_category = _s(state.get("failure_category"))
    urgency = _s(state.get("urgency"), "MEDIUM")
    recoverability_score = float(state.get("recoverability_score") or 0.5)
    amount = float(state.get("amount_inr") or 0.0)
    pref_channel = _s(state.get("contact_channel_pref"), "whatsapp").lower()
    
    # -------------------------------------------------------------
    # STOPPING RULES EVALUATION
    # -------------------------------------------------------------
    stopping_rule = None
    
    if prior_attempts >= 3:
        stopping_rule = "MAX_ATTEMPTS_EXCEEDED (prior_attempts >= 3)"
    elif risk_score >= 0.80:
        stopping_rule = "HIGH_FRAUD_RISK_THRESHOLD (risk_score >= 0.80)"
    elif failure_category == "IRRECOVERABLE_OR_REVOKED":
        stopping_rule = "PERMANENT_DECLINE_OR_REVOKED_MANDATE"
    elif recoverability_score < 0.20:
        stopping_rule = "LOW_RECOVERABILITY_SCORE (< 0.20)"
        
    if stopping_rule:
        action = "ESCALATE_HUMAN" if (risk_score >= 0.80 and amount >= 50000) else "NO_ACTION_STOP"
        reason = f"Execution halted by stopping rule: {stopping_rule}. Recoverability={recoverability_score}, PriorAttempts={prior_attempts}, RiskScore={risk_score}."
        return {
            "action": action,
            "channel_selected": "none" if action == "NO_ACTION_STOP" else "internal_flag",
            "reason_string": reason,
            "stopping_rule_triggered": stopping_rule,
            "recommended_delay_mins": 0,
            "script_template_key": "none"
        }
        
    # -------------------------------------------------------------
    # INTERVENTION SELECTION LOGIC
    # -------------------------------------------------------------
    action = "NUDGE_WHATSAPP"
    channel_selected = pref_channel
    recommended_delay = 0
    script_key = "default_nudge"
    
    # Rule 1: Auto-Retry for transient bank issues on first failure
    if failure_category == "TRANSIENT_BANK_ERROR" and prior_attempts == 0:
        action = "AUTO_RETRY"
        channel_selected = "system_gateway"
        recommended_delay = 15  # Retry in 15 mins to allow gateway recovery
        script_key = "auto_retry_stub"
        reason = f"Transient bank error detected with prior_attempts=0. Triggering automated gateway retry in {recommended_delay}m. Recoverability={recoverability_score}."

    # Rule 2: High Value or High Urgency or Voice Preference -> Voice Call Intervention
    elif (urgency in ["CRITICAL", "HIGH"] and amount >= 10000) or pref_channel == "voice" or sub_reason in ["invoice_dispute", "price_hesitation"]:
        action = "VOICE_CALL"
        channel_selected = "voice"
        recommended_delay = 5 if urgency == "CRITICAL" else 30
        script_key = f"voice_{sub_reason}"
        reason = f"Selected Voice Call due to high urgency ({urgency}), transaction value (₹{amount:,.2f}), or explicit channel preference. Recoverability={recoverability_score}."

    # Rule 3: B2B Overdue Invoice -> Email or WhatsApp Nudge
    elif failure_category == "B2B_INVOICE_PENDING":
        action = "NUDGE_EMAIL" if pref_channel == "email" else "NUDGE_WHATSAPP"
        channel_selected = pref_channel if pref_channel in ["email", "whatsapp"] else "email"
        recommended_delay = 60
        script_key = "invoice_reminder_nudge"
        reason = f"B2B Overdue Invoice categorized. Dispatching formal {action} with instant payment link. Recoverability={recoverability_score}."

    # Rule 4: Standard Consumer Recoverable Failures (Card Expired, Insufficient Funds, OTP Abandon)
    else:
        if pref_channel == "sms":
            action = "NUDGE_SMS"
        elif pref_channel == "email":
            action = "NUDGE_EMAIL"
        else:
            action = "NUDGE_WHATSAPP"
            
        channel_selected = pref_channel
        recommended_delay = 0 if sub_reason in ["otp_abandon", "wrong_cvv_otp_fail"] else 120
        script_key = f"nudge_{sub_reason}"
        reason = f"Recoverable {failure_category} ({sub_reason}). Dispatching low-cost interactive {action} on preferred channel ({channel_selected}). Recoverability={recoverability_score}."

    return {
        "action": action,
        "channel_selected": channel_selected,
        "reason_string": reason,
        "stopping_rule_triggered": None,
        "recommended_delay_mins": recommended_delay,
        "script_template_key": script_key
    }

# Build LangGraph State Graph
def build_triage_graph():
    builder = StateGraph(PaymentEventState)
    
    # Add Nodes
    builder.add_node("classify_failure", classify_failure_node)
    builder.add_node("decide_action", decide_action_node)
    
    # Set Edges
    builder.set_entry_point("classify_failure")
    builder.add_edge("classify_failure", "decide_action")
    builder.add_edge("decide_action", END)
    
    return builder.compile()

# Standalone execution test helper
def process_single_event(event_dict: Dict[str, Any], app=None) -> PaymentEventState:
    if app is None:
        app = build_triage_graph()
    result = app.invoke(event_dict)
    return result

if __name__ == "__main__":
    print("Testing LangGraph Payment Triage Graph on sample event...")
    sample_event = {
        "event_id": "evt_test_001",
        "customer_id": "cust_101",
        "customer_name": "Priya Sharma",
        "city": "Mumbai",
        "failure_type": "subscription_lapse",
        "sub_reason": "card_expired",
        "amount_inr": 2499.00,
        "currency": "INR",
        "failed_at": "2026-08-31T09:00:00Z",
        "detected_at": "2026-08-31T10:00:00Z",
        "contact_channel_pref": "whatsapp",
        "language_pref": "hinglish",
        "prior_attempts": 0,
        "risk_score": 0.15,
        "phone_masked": "+91-XXXXX-98765",
        "do_not_disturb_hours": "22:00-08:00 IST"
    }
    
    graph = build_triage_graph()
    output = process_single_event(sample_event, graph)
    
    print("\n--- TRIAGE GRAPH OUTPUT ---")
    print(f"Event ID      : {output['event_id']}")
    print(f"Failure Profile: {output['failure_category']} ({output['sub_reason']})")
    print(f"Recoverability: {output['recoverability_score']} | Urgency: {output['urgency']}")
    print(f"Action Chosen : {output['action']} (Channel: {output['channel_selected']})")
    print(f"Reason String : {output['reason_string']}")
    print(f"Stopping Rule : {output['stopping_rule_triggered']}")
