"""
CLI: simulate Razorpay test-mode checkouts into the recovery app.

Uses documented test PANs, random CVV, future expiry, and mock ACS
Success / Failure buttons from:
https://razorpay.com/docs/payments/payments/test-card-details/
"""

from __future__ import annotations

import argparse
import json
import sys
import time

import requests

from payment_workflow import TEST_CARDS, simulate_checkout

BASE_URL_DEFAULT = "http://127.0.0.1:8000"

DEMO_SCENARIOS = [
    {
        "name": "Happy path - Indian Visa",
        "card_number": "4100 2800 0000 1007",
        "cvv": "123",
        "expiry": "12/29",
        "amount_inr": 2499.00,
        "customer_name": "Neha Kapoor",
        "city": "Mumbai",
        "bank_action": "success",
        "contact_channel_pref": "whatsapp",
    },
    {
        "name": "Mock ACS Failure - authentication",
        "card_number": "5500 6700 0000 1002",
        "cvv": "456",
        "expiry": "11/28",
        "amount_inr": 12500.00,
        "customer_name": "Arjun Mehta",
        "city": "Bangalore",
        "bank_action": "failure",
        "failure_reason": "wrong_cvv_otp_fail",
        "contact_channel_pref": "voice",
    },
    {
        "name": "Insufficient funds test PAN",
        "card_number": "4100 2800 0008 0001",
        "cvv": "999",
        "expiry": "09/30",
        "amount_inr": 3500.00,
        "customer_name": "Priya Das",
        "city": "Kolkata",
        "bank_action": "failure",
        "contact_channel_pref": "whatsapp",
    },
    {
        "name": "Issuer decline test PAN",
        "card_number": "4100 2800 0006 0003",
        "cvv": "321",
        "expiry": "08/27",
        "amount_inr": 8900.00,
        "customer_name": "Rohan Nair",
        "city": "Hyderabad",
        "bank_action": "failure",
        "contact_channel_pref": "sms",
    },
    {
        "name": "Expired card (past expiry)",
        "card_number": "4384 7968 2770 3274",
        "cvv": "111",
        "expiry": "01/20",
        "amount_inr": 1999.00,
        "customer_name": "Kavita Iyer",
        "city": "Delhi",
        "bank_action": "success",
        "contact_channel_pref": "email",
    },
    {
        "name": "International Mastercard + ACS Failure",
        "card_number": "5421 1393 0609 0628",
        "cvv": "777",
        "expiry": "03/28",
        "amount_inr": 18750.00,
        "customer_name": "Aarav Gupta",
        "city": "Pune",
        "bank_action": "failure",
        "failure_reason": "otp_abandon",
        "contact_channel_pref": "voice",
    },
    {
        "name": "RuPay success",
        "card_number": "6527 6589 0000 1005",
        "cvv": "258",
        "expiry": "06/29",
        "amount_inr": 799.00,
        "customer_name": "Saanvi Reddy",
        "city": "Chennai",
        "bank_action": "success",
        "contact_channel_pref": "whatsapp",
    },
]


def _print_result(title: str, payload: dict) -> None:
    checkout = payload.get("checkout", {})
    recovery = payload.get("recovery")
    print(f"\n========== {title} ==========")
    print(f"Customer : {checkout.get('customer_name')}")
    print(f"Amount   : INR {checkout.get('amount_inr')}")
    print(f"Card     : ****{checkout.get('card_last4')} ({checkout.get('card_label')})")
    print(f"Gateway  : {checkout.get('gateway_status')}")
    if checkout.get("authorized"):
        print("Result   : CAPTURED - no recovery agent")
        return
    print(f"Failure  : {checkout.get('sub_reason')}")
    print(f"Event    : {checkout.get('event_id')}")
    if recovery:
        triage = recovery.get("triage") or {}
        print(
            f"Triage   : {triage.get('action')} | urgency={triage.get('urgency')} | score={triage.get('recoverability_score')}"
        )
        reason = str(triage.get("reason_string") or "").replace("\u20b9", "Rs.")
        print(f"Reason   : {reason}")
        voice = recovery.get("voice_call") or {}
        if voice.get("agent_opening_text"):
            print(f"Agent    : {voice.get('agent_opening_text')}")
        link = recovery.get("payment_link") or {}
        if link.get("short_url"):
            print(f"Pay link : {link.get('short_url')} ({link.get('plink_id')})")
        print(f"Recovered: {recovery.get('recovered')}")


def run_via_api(base_url: str) -> int:
    health_ok = False
    try:
        r = requests.get(f"{base_url}/api/metrics", timeout=3)
        health_ok = r.status_code == 200
    except requests.RequestException:
        health_ok = False

    if not health_ok:
        print(f"Server not reachable at {base_url}. Running locally (no live voice TTS).")
        return run_local()

    print(f"Posting {len(DEMO_SCENARIOS)} test-mode checkouts to {base_url} ...")
    failures = 0
    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        body = {k: v for k, v in scenario.items() if k != "name"}
        try:
            res = requests.post(f"{base_url}/api/payments/simulate", json=body, timeout=60)
            res.raise_for_status()
            _print_result(f"{i}/{len(DEMO_SCENARIOS)} {scenario['name']}", res.json())
        except Exception as exc:
            failures += 1
            print(f"\nFAILED {scenario['name']}: {exc}")
        time.sleep(0.4)

    try:
        metrics = requests.get(f"{base_url}/api/metrics", timeout=10).json()
        print("\n========== LIVE DASHBOARD METRICS ==========")
        print(json.dumps({k: metrics[k] for k in metrics if k not in ("by_reason", "by_action", "funnel")}, indent=2))
        print("Funnel:", json.dumps(metrics.get("funnel"), indent=2))
    except Exception as exc:
        print("Could not fetch metrics:", exc)
        failures += 1
    return 1 if failures else 0


def run_local() -> int:
    from voice_service import VoiceLLMCallingEngine

    engine = VoiceLLMCallingEngine()
    for i, scenario in enumerate(DEMO_SCENARIOS, 1):
        body = {k: v for k, v in scenario.items() if k != "name"}
        payload = simulate_checkout(**body, voice_engine=engine)
        _print_result(f"{i}/{len(DEMO_SCENARIOS)} {scenario['name']}", payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Simulate Razorpay test-card payments into the recovery app.")
    parser.add_argument("--base-url", default=BASE_URL_DEFAULT)
    parser.add_argument("--local", action="store_true", help="Skip HTTP and run workflow in-process.")
    parser.add_argument("--list-cards", action="store_true")
    args = parser.parse_args()

    if args.list_cards:
        print("Razorpay test PANs loaded:")
        for pan, meta in TEST_CARDS.items():
            print(f"  {pan}  {meta['network']:<12} {meta['region']:<5} {meta['label']}")
        return 0

    if args.local:
        return run_local()
    return run_via_api(args.base_url.rstrip("/"))


if __name__ == "__main__":
    sys.exit(main())
