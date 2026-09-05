import random
import csv
from datetime import datetime, timedelta

def generate_synthetic_events(count=150, filename="events.csv"):
    random.seed(42)
    
    first_names = ["Aarav", "Priya", "Rohan", "Ananya", "Vikram", "Kavita", "Deepak", "Saanvi", "Rahul", "Myra", 
                   "Ishaan", "Pooja", "Arjun", "Riya", "Suresh", "Navya", "Amit", "Kiara", "Sai", "Diya"]
    last_names = ["Sharma", "Nair", "Gupta", "Desai", "Patel", "Iyer", "Mehta", "Malhotra", "Shah", "Reddy", 
                  "Agarwal", "Kapoor", "Vera", "Chopra", "Kumar", "Bansal", "Pillai", "Rao", "Joshi", "Verma"]
    cities = ["Mumbai", "Bangalore", "Delhi", "Hyderabad", "Pune", "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Indore", "Chandigarh", "Lucknow"]
    
    # Skewed failure failure_types & sub_reasons according to real payment recovery stats:
    # 35% Insufficient funds (Soft decline - recoverable)
    # 25% Card expired / mandate (Soft decline - recoverable)
    # 15% OTP abandon / payment page drop (Checkout abandonment - recoverable via nudge)
    # 10% Bank decline / technical error (Soft decline - auto-retry candidate)
    # 10% Overdue invoice / cash flow delay (B2B recoverable via voice/email)
    # 5%  Genuine abandonment / mandate revoked (Low recoverability)
    
    failure_scenarios = [
        ("failed_payment", "insufficient_funds", 0.35, (500, 15000)),
        ("subscription_lapse", "card_expired", 0.25, (299, 5000)),
        ("abandoned_checkout", "otp_abandon", 0.10, (999, 25000)),
        ("abandoned_checkout", "payment_page_drop", 0.05, (499, 15000)),
        ("failed_payment", "bank_decline", 0.10, (1000, 30000)),
        ("overdue_invoice", "cash_flow_delay", 0.05, (15000, 250000)),
        ("overdue_invoice", "forgotten", 0.03, (10000, 150000)),
        ("abandoned_checkout", "genuine_abandonment", 0.04, (2000, 20000)),
        ("subscription_lapse", "mandate_revoked", 0.03, (499, 5000)),
    ]
    
    scenarios_pool = []
    for ftype, sreason, weight, amt_range in failure_scenarios:
        scenarios_pool.extend([(ftype, sreason, amt_range)] * int(weight * 100))
    
    channels = ["whatsapp", "sms", "voice", "email"]
    channel_weights = [0.45, 0.25, 0.20, 0.10]
    
    languages = ["hinglish", "hindi", "english"]
    lang_weights = [0.50, 0.30, 0.20]
    
    base_time = datetime(2026, 8, 31, 10, 0, 0)
    
    rows = []
    for i in range(1, count + 1):
        evt_id = f"evt_{random.randint(100000, 999999):x}"
        cust_id = f"cust_{random.randint(1000, 9999):x}"
        name = f"{random.choice(first_names)} {random.choice(last_names)}"
        city = random.choice(cities)
        
        ftype, sreason, amt_range = random.choice(scenarios_pool)
        amount = round(random.uniform(amt_range[0], amt_range[1]), 2)
        
        # Hours ago
        hours_ago = random.randint(1, 144)
        failed_at = (base_time - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")
        detected_at = base_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        channel_pref = random.choices(channels, weights=channel_weights)[0]
        lang_pref = random.choices(languages, weights=lang_weights)[0]
        
        # Prior attempts skew: mostly 0 or 1, few 2 or 3
        prior_attempts = random.choices([0, 1, 2, 3], weights=[0.60, 0.25, 0.10, 0.05])[0]
        
        # Risk score: mostly low (0.05 - 0.40), few medium/high
        risk_score = round(random.choices(
            [random.uniform(0.05, 0.40), random.uniform(0.40, 0.70), random.uniform(0.70, 0.95)],
            weights=[0.75, 0.20, 0.05]
        )[0], 2)
        
        phone_masked = f"+91-XXXXX-{random.randint(10000, 99999)}"
        dnd_hours = "22:00-08:00 IST"
        
        rows.append({
            "event_id": evt_id,
            "customer_id": cust_id,
            "customer_name": name,
            "city": city,
            "failure_type": ftype,
            "sub_reason": sreason,
            "amount_inr": amount,
            "currency": "INR",
            "failed_at": failed_at,
            "detected_at": detected_at,
            "contact_channel_pref": channel_pref,
            "language_pref": lang_pref,
            "prior_attempts": prior_attempts,
            "risk_score": risk_score,
            "phone_masked": phone_masked,
            "do_not_disturb_hours": dnd_hours
        })
        
    fieldnames = list(rows[0].keys())
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        
    print(f"Generated {count} synthetic payment failure events in '{filename}'.")

if __name__ == "__main__":
    generate_synthetic_events(150, "events.csv")
