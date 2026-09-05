"""
Razorpay test-mode checkout simulation + recovery workflow.

Test cards and checkout steps follow:
https://razorpay.com/docs/payments/payments/test-card-details/
Indian / decline scenarios also use documented Razorpay test numbers
(Visa 4100 2800 0000 1007, decline 4100 2800 0006 0003, etc.).
"""

from __future__ import annotations

import json
import logging
import random
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from execution_tools import ExecutionTools
from outcome_simulator import OutcomeSimulator
from razorpay_integration import razorpay_manager
from triage_graph import process_single_event

BASE_DIR = Path(__file__).resolve().parent
EVENTS_CSV = BASE_DIR / "events.csv"
LEDGER_FILE = BASE_DIR / "payment_ledger.json"

logger = logging.getLogger("PaymentWorkflow")

# Official / documented Razorpay test cards (PAN only; CVV any; expiry any future date).
TEST_CARDS: Dict[str, Dict[str, Any]] = {
    # India — Standard Checkout / plugin docs
    "4100280000001007": {
        "network": "Visa",
        "region": "IN",
        "label": "Indian Visa (happy path)",
        "forced_reason": None,
    },
    "5500670000001002": {
        "network": "Mastercard",
        "region": "IN",
        "label": "Indian Mastercard",
        "forced_reason": None,
    },
    "6527658900001005": {
        "network": "RuPay",
        "region": "IN",
        "label": "Indian RuPay",
        "forced_reason": None,
    },
    "36082800091007": {
        "network": "Diners",
        "region": "IN",
        "label": "Indian Diners",
        "forced_reason": None,
    },
    "340256000401007": {
        "network": "Amex",
        "region": "IN",
        "label": "Indian Amex",
        "forced_reason": None,
    },
    "4100280000060003": {
        "network": "Visa",
        "region": "IN",
        "label": "Indian Visa — card declined",
        "forced_reason": "bank_decline",
    },
    "4100280000080001": {
        "network": "Visa",
        "region": "IN",
        "label": "Indian Visa — insufficient funds",
        "forced_reason": "insufficient_funds",
    },
    # United States — test-card-details docs
    "4384796827703274": {
        "network": "Visa",
        "region": "US",
        "label": "US Visa",
        "forced_reason": None,
    },
    "5312686556779641": {
        "network": "Mastercard",
        "region": "US",
        "label": "US Mastercard",
        "forced_reason": None,
    },
    "378282246310005": {
        "network": "Amex",
        "region": "US",
        "label": "US Amex",
        "forced_reason": None,
    },
    "6594730000000001": {
        "network": "Diners",
        "region": "US",
        "label": "US Diners",
        "forced_reason": None,
    },
    # International — test-card-details docs
    "4239536006315640": {
        "network": "Visa",
        "region": "INTL",
        "label": "International Visa",
        "forced_reason": None,
    },
    "5421139306090628": {
        "network": "Mastercard",
        "region": "INTL",
        "label": "International Mastercard",
        "forced_reason": None,
    },
    "377984908869514": {
        "network": "Amex",
        "region": "INTL",
        "label": "International Amex",
        "forced_reason": None,
    },
    "6011083327337267": {
        "network": "Discover",
        "region": "INTL",
        "label": "International Discover",
        "forced_reason": None,
    },
}

EVENT_COLUMNS = [
    "event_id",
    "customer_id",
    "customer_name",
    "city",
    "failure_type",
    "sub_reason",
    "amount_inr",
    "currency",
    "failed_at",
    "detected_at",
    "contact_channel_pref",
    "language_pref",
    "prior_attempts",
    "risk_score",
    "phone_masked",
    "do_not_disturb_hours",
    "status",
]


def normalize_pan(card_number: str) -> str:
    return "".join(ch for ch in str(card_number) if ch.isdigit())


def load_events_df() -> pd.DataFrame:
    if EVENTS_CSV.exists():
        df = pd.read_csv(EVENTS_CSV)
        if "status" not in df.columns:
            df["status"] = "OPEN"
        df["status"] = df["status"].fillna("OPEN")
        return df
    return pd.DataFrame(columns=EVENT_COLUMNS)


def save_events_df(df: pd.DataFrame) -> None:
    df.to_csv(EVENTS_CSV, index=False)


def load_ledger() -> List[Dict[str, Any]]:
    if LEDGER_FILE.exists():
        try:
            return json.loads(LEDGER_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_ledger(rows: List[Dict[str, Any]]) -> None:
    LEDGER_FILE.write_text(json.dumps(rows, indent=2, default=str), encoding="utf-8")


def _expiry_is_past(expiry: str) -> bool:
    raw = (expiry or "").strip().replace(" ", "")
    if not raw:
        return False
    try:
        if "/" in raw:
            mm_s, yy_s = raw.split("/", 1)
        elif len(raw) == 4:
            mm_s, yy_s = raw[:2], raw[2:]
        else:
            return False
        month = int(mm_s)
        year = int(yy_s)
        if year < 100:
            year += 2000
        if month < 1 or month > 12:
            return True
        now = datetime.now()
        return (year, month) < (now.year, now.month)
    except (ValueError, TypeError):
        return False


def authorize_test_payment(
    card_number: str,
    cvv: str,
    expiry: str,
    bank_action: str,
    failure_reason: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Replicates Razorpay test-mode checkout:
    valid test PAN + any CVV + future expiry, then mock bank Success / Failure.
    """
    pan = normalize_pan(card_number)
    meta = TEST_CARDS.get(pan)

    if not meta:
        return {
            "authorized": False,
            "gateway_status": "failed",
            "sub_reason": "invalid_card_input",
            "failure_type": "failed_payment",
            "error_description": "card issuer is invalid or invalid card input (not a Razorpay test PAN).",
            "card_meta": None,
        }

    if _expiry_is_past(expiry):
        return {
            "authorized": False,
            "gateway_status": "failed",
            "sub_reason": "card_expired",
            "failure_type": "subscription_lapse",
            "error_description": "Expired card (docs: any past date tests expiry handling).",
            "card_meta": meta,
        }

    if not str(cvv).strip():
        return {
            "authorized": False,
            "gateway_status": "failed",
            "sub_reason": "wrong_cvv_otp_fail",
            "failure_type": "failed_payment",
            "error_description": "CVV required (docs: any random CVV in test mode).",
            "card_meta": meta,
        }

    forced = meta.get("forced_reason")
    if forced:
        ftype = "subscription_lapse" if forced == "card_expired" else "failed_payment"
        return {
            "authorized": False,
            "gateway_status": "failed",
            "sub_reason": forced,
            "failure_type": ftype,
            "error_description": f"Issuer response from mapped test card ({meta['label']}).",
            "card_meta": meta,
        }

    action = (bank_action or "success").lower()
    if action in ("success", "authorized", "captured"):
        return {
            "authorized": True,
            "gateway_status": "captured",
            "sub_reason": None,
            "failure_type": None,
            "error_description": None,
            "card_meta": meta,
        }

    reason = failure_reason or "authentication_failed"
    failure_type = "abandoned_checkout" if reason in ("otp_abandon", "wrong_cvv_otp_fail") else "failed_payment"
    return {
        "authorized": False,
        "gateway_status": "failed",
        "sub_reason": reason,
        "failure_type": failure_type,
        "error_description": "Mock ACS Failure (Razorpay test-mode bank page).",
        "card_meta": meta,
    }


def _append_failed_event(event: Dict[str, Any]) -> None:
    df = load_events_df()
    row = {col: event.get(col, "") for col in EVENT_COLUMNS}
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    save_events_df(df)


def mark_event_recovered(event_id: str) -> None:
    df = load_events_df()
    if df.empty or "event_id" not in df.columns:
        return
    df.loc[df["event_id"] == event_id, "status"] = "RECOVERED"
    save_events_df(df)


def _build_event_row(
    *,
    customer_name: str,
    amount_inr: float,
    sub_reason: str,
    failure_type: str,
    city: str,
    contact_channel_pref: str,
    language_pref: str,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    event_id = f"evt_{uuid.uuid4().hex[:6]}"
    return {
        "event_id": event_id,
        "customer_id": f"cust_{uuid.uuid4().hex[:4]}",
        "customer_name": customer_name,
        "city": city,
        "failure_type": failure_type,
        "sub_reason": sub_reason,
        "amount_inr": float(amount_inr),
        "currency": "INR",
        "failed_at": now,
        "detected_at": now,
        "contact_channel_pref": contact_channel_pref,
        "language_pref": language_pref,
        "prior_attempts": 0,
        "risk_score": 0.12,
        "phone_masked": f"+91-XXXXX-{random.randint(10000, 99999)}",
        "do_not_disturb_hours": "22:00-08:00 IST",
        "status": "OPEN",
    }


def run_recovery_workflow(event: Dict[str, Any], voice_engine=None) -> Dict[str, Any]:
    """LangGraph triage → cheapest-first tools → optional voice + payment link → outcome."""
    triage = process_single_event(dict(event))
    action = triage.get("action", "NO_ACTION_STOP")

    if str(action).startswith("NUDGE"):
        tool_output = ExecutionTools.execute_nudge(triage)
    elif action == "AUTO_RETRY":
        tool_output = ExecutionTools.execute_payment_retry(triage)
    elif action == "VOICE_CALL":
        tool_output = ExecutionTools.generate_voice_agent_payload(triage)
    else:
        tool_output = {"status": "SKIPPED_OR_STOPPED", "estimated_cost_inr": 0.0}

    voice_call = None
    if action == "VOICE_CALL" and voice_engine is not None:
        try:
            voice_call = voice_engine.start_call(triage, voice_agent_id="swara_hi")
        except Exception as exc:
            logger.warning("Voice engine failed: %s", exc)
            voice_call = {"error": str(exc)}

    link_data = None
    if action not in ("NO_ACTION_STOP",):
        link_data = razorpay_manager.create_payment_link(
            event["event_id"],
            event.get("customer_name", "Customer"),
            float(event.get("amount_inr", 0)),
            event.get("sub_reason", "payment_failed"),
        )

    outcome = OutcomeSimulator.simulate_event_outcome(triage)
    recovered = bool(outcome.get("is_recovered"))

    # Auto-retry captured at gateway counts as recovered even if later sim would fail.
    if action == "AUTO_RETRY" and tool_output.get("response", {}).get("gateway_status") == "captured":
        recovered = True
        outcome["is_recovered"] = True
        outcome["outcome_status"] = "RECOVERED_SUCCESS"
        outcome["amount_recovered_inr"] = float(event.get("amount_inr", 0))

    webhook = None
    if recovered and link_data:
        webhook = razorpay_manager.handle_webhook_payment_captured(event["event_id"], "card")
        mark_event_recovered(event["event_id"])
        event["status"] = "RECOVERED"
    else:
        df = load_events_df()
        if not df.empty:
            df.loc[df["event_id"] == event["event_id"], "status"] = action
            save_events_df(df)
        event["status"] = action

    return {
        "triage": {
            "recoverability_score": triage.get("recoverability_score"),
            "urgency": triage.get("urgency"),
            "failure_category": triage.get("failure_category"),
            "action": action,
            "channel_selected": triage.get("channel_selected"),
            "reason_string": triage.get("reason_string"),
            "stopping_rule_triggered": triage.get("stopping_rule_triggered"),
        },
        "tool_output": tool_output,
        "voice_call": {
            "agent_name": (voice_call or {}).get("agent_name"),
            "agent_opening_text": (voice_call or {}).get("agent_opening_text"),
        }
        if voice_call
        else None,
        "payment_link": link_data,
        "outcome": outcome,
        "webhook": webhook,
        "recovered": recovered,
    }


def simulate_checkout(
    *,
    card_number: str,
    cvv: str = "123",
    expiry: str = "12/29",
    amount_inr: float = 5000.0,
    customer_name: str = "Test Customer",
    city: str = "Mumbai",
    contact_channel_pref: str = "voice",
    language_pref: str = "hinglish",
    bank_action: str = "success",
    failure_reason: Optional[str] = None,
    voice_engine=None,
) -> Dict[str, Any]:
    auth = authorize_test_payment(card_number, cvv, expiry, bank_action, failure_reason)
    payment_id = f"pay_{uuid.uuid4().hex[:10]}"
    pan = normalize_pan(card_number)
    last4 = pan[-4:] if len(pan) >= 4 else pan

    record: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payment_id": payment_id,
        "customer_name": customer_name,
        "amount_inr": float(amount_inr),
        "card_last4": last4,
        "card_network": (auth.get("card_meta") or {}).get("network"),
        "card_region": (auth.get("card_meta") or {}).get("region"),
        "card_label": (auth.get("card_meta") or {}).get("label"),
        "bank_action": bank_action,
        "gateway_status": auth["gateway_status"],
        "authorized": auth["authorized"],
        "sub_reason": auth.get("sub_reason"),
        "event_id": None,
        "agent_launched": False,
        "recovered": False,
        "action": None,
    }

    recovery = None
    if auth["authorized"]:
        record["message"] = "Payment captured in Razorpay test mode. No recovery agent required."
    else:
        event = _build_event_row(
            customer_name=customer_name,
            amount_inr=amount_inr,
            sub_reason=auth["sub_reason"] or "payment_failed",
            failure_type=auth["failure_type"] or "failed_payment",
            city=city,
            contact_channel_pref=contact_channel_pref,
            language_pref=language_pref,
        )
        _append_failed_event(event)
        record["event_id"] = event["event_id"]
        recovery = run_recovery_workflow(event, voice_engine=voice_engine)
        record["agent_launched"] = recovery["triage"]["action"] not in ("NO_ACTION_STOP", None)
        record["recovered"] = recovery["recovered"]
        record["action"] = recovery["triage"]["action"]
        record["message"] = auth.get("error_description") or "Payment failed; recovery workflow executed."

    ledger = load_ledger()
    ledger.append(record)
    save_ledger(ledger)

    return {"checkout": record, "recovery": recovery, "auth": auth}


def compute_metrics() -> Dict[str, Any]:
    events = load_events_df()
    ledger = load_ledger()

    failed_count = int(len(events)) if not events.empty else 0
    failed_volume = float(events["amount_inr"].sum()) if not events.empty else 0.0

    if not events.empty:
        recovered_mask = events["status"].astype(str).str.upper() == "RECOVERED"
        recovered_count = int(recovered_mask.sum())
        recovered_volume = float(events.loc[recovered_mask, "amount_inr"].sum())
        open_count = failed_count - recovered_count
        open_volume = failed_volume - recovered_volume
    else:
        recovered_count = recovered_volume = open_count = open_volume = 0

    retrieval_count = (recovered_count / failed_count * 100) if failed_count else 0.0
    retrieval_volume = (recovered_volume / failed_volume * 100) if failed_volume else 0.0
    avg_ticket = (failed_volume / failed_count) if failed_count else 0.0

    intervention_cost = recovered_count * 1.20 + (failed_count - recovered_count) * 0.40
    net_value = recovered_volume - intervention_cost
    roi = (net_value / intervention_cost) if intervention_cost else 0.0

    by_reason: List[Dict[str, Any]] = []
    if not events.empty:
        grp = events.groupby(events["sub_reason"].fillna("unknown"), dropna=False)
        for reason, g in grp:
            rec = g["status"].astype(str).str.upper().eq("RECOVERED")
            by_reason.append(
                {
                    "reason": str(reason),
                    "count": int(len(g)),
                    "volume": round(float(g["amount_inr"].sum()), 2),
                    "recovered": int(rec.sum()),
                    "retrieval_rate_pct": round(float(rec.sum() / len(g) * 100), 1) if len(g) else 0.0,
                }
            )
        by_reason.sort(key=lambda x: x["count"], reverse=True)

    attempts = len(ledger)
    checkout_ok = sum(1 for r in ledger if r.get("authorized"))
    checkout_fail_rows = [r for r in ledger if not r.get("authorized")]
    checkout_fail = len(checkout_fail_rows)
    agent_launched = sum(1 for r in ledger if r.get("agent_launched"))
    sim_recovered_rows = [r for r in ledger if r.get("recovered")]
    sim_recovered = len(sim_recovered_rows)
    live_failed_volume = sum(float(r.get("amount_inr") or 0) for r in checkout_fail_rows)
    live_recovered_volume = sum(float(r.get("amount_inr") or 0) for r in sim_recovered_rows)
    live_retrieval_count = (sim_recovered / checkout_fail * 100) if checkout_fail else 0.0
    live_retrieval_volume = (live_recovered_volume / live_failed_volume * 100) if live_failed_volume else 0.0

    by_action: Dict[str, int] = {}
    for r in ledger:
        act = r.get("action")
        if act:
            by_action[act] = by_action.get(act, 0) + 1
    if not events.empty:
        for status in events["status"].dropna().astype(str):
            if status.upper() not in ("OPEN", "RECOVERED", "NAN", ""):
                by_action[status] = by_action.get(status, 0) + 1

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checkout_attempts": attempts,
        "checkout_success": checkout_ok,
        "checkout_failed": checkout_fail,
        "authorization_rate_pct": round(checkout_ok / attempts * 100, 1) if attempts else 0.0,
        "live_failed_count": checkout_fail,
        "live_failed_volume_inr": round(live_failed_volume, 2),
        "live_recovered_count": sim_recovered,
        "live_recovered_volume_inr": round(live_recovered_volume, 2),
        "live_retrieval_rate_count_pct": round(live_retrieval_count, 1),
        "live_retrieval_rate_volume_pct": round(live_retrieval_volume, 1),
        "failed_payments_count": failed_count,
        "failed_volume_inr": round(failed_volume, 2),
        "recovered_count": recovered_count,
        "recovered_volume_inr": round(recovered_volume, 2),
        "open_count": open_count,
        "open_volume_inr": round(open_volume, 2),
        "retrieval_rate_count_pct": round(retrieval_count, 1),
        "retrieval_rate_volume_pct": round(retrieval_volume, 1),
        "avg_failed_ticket_inr": round(avg_ticket, 2),
        "intervention_cost_inr": round(intervention_cost, 2),
        "net_value_added_inr": round(net_value, 2),
        "roi_multiplier": round(roi, 1),
        "agent_launched": agent_launched,
        "simulated_recoveries": sim_recovered,
        "by_reason": by_reason[:12],
        "by_action": by_action,
        "funnel": {
            "checkout_attempts": attempts,
            "failed": checkout_fail if attempts else failed_count,
            "agent_launched": agent_launched,
            "recovered": sim_recovered if attempts else recovered_count,
        },
    }
