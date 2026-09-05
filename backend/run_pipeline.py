"""
End-to-End Execution Pipeline & Audit Logger
Processes events dataset through LangGraph triage, executes tools, simulates outcomes,
and saves complete audit log deliverable.
"""

import pandas as pd
import json
from datetime import datetime
from triage_graph import build_triage_graph, process_single_event
from execution_tools import ExecutionTools
from outcome_simulator import OutcomeSimulator

def run_full_pipeline(csv_path="events.csv", output_csv="audit_log.csv", output_json="audit_log.json"):
    print("=" * 80)
    print("STARTING RAZORPAY PAYMENT RECOVERY & INTERVENTION ENGINE PIPELINE")
    print("=" * 80)
    
    # 1. Load Dataset
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} synthetic payment failure events from '{csv_path}'.\n")
    
    # 2. Initialize LangGraph Engine
    triage_app = build_triage_graph()
    
    pipeline_results = []
    
    print("Running LangGraph Triage & Decision Node over dataset...")
    for idx, row in df.iterrows():
        event_dict = row.to_dict()

        # Sanitize: pandas NaN becomes float('nan') which crashes .lower() on string fields
        str_fields = [
            "event_id", "customer_id", "customer_name", "city",
            "failure_type", "sub_reason", "currency", "failed_at",
            "detected_at", "contact_channel_pref", "language_pref",
            "phone_masked", "do_not_disturb_hours",
        ]
        for f in str_fields:
            v = event_dict.get(f)
            if v is None or (isinstance(v, float) and v != v):  # nan check
                event_dict[f] = ""
            else:
                event_dict[f] = str(v)

        # Ensure numeric fields are correct types
        event_dict["amount_inr"] = float(event_dict.get("amount_inr") or 0.0)
        event_dict["risk_score"] = float(event_dict.get("risk_score") or 0.0)
        try:
            event_dict["prior_attempts"] = int(event_dict.get("prior_attempts") or 0)
        except (ValueError, TypeError):
            event_dict["prior_attempts"] = 0

        # Step 2 & 3: Triage graph execution
        triage_state = process_single_event(event_dict, app=triage_app)
        
        # Step 4: Tool Execution Stub based on action decision
        action = triage_state.get("action")
        tool_output = {}
        
        if action.startswith("NUDGE"):
            tool_output = ExecutionTools.execute_nudge(triage_state)
        elif action == "AUTO_RETRY":
            tool_output = ExecutionTools.execute_payment_retry(triage_state)
        elif action == "VOICE_CALL":
            tool_output = ExecutionTools.generate_voice_agent_payload(triage_state)
        else:
            tool_output = {"status": "SKIPPED_OR_STOPPED", "estimated_cost_inr": 0.00}
            
        merged_item = {
            **triage_state,
            "tool_execution_status": tool_output.get("status"),
            "tool_output_details": json.dumps(tool_output)
        }
        
        pipeline_results.append(merged_item)
        
    # 3. Step 5: Run Outcome Simulation & Executive Metrics
    print("Simulating outcome probabilities and recovery metrics...")
    sim_results = OutcomeSimulator.run_simulation_suite(pipeline_results)
    
    summary = sim_results["summary_metrics"]
    action_breakdown = sim_results["action_breakdown"]
    detailed_records = sim_results["detailed_records"]
    
    # 4. Save Audit Log Deliverables
    audit_df = pd.DataFrame(detailed_records)
    audit_df.to_csv(output_csv, index=False)
    
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(sim_results, f, indent=2, default=str)
        
    print(f"\nSaved complete audit log deliverable to '{output_csv}' and '{output_json}'.\n")
    
    # 5. Print Executive Dashboard Summary
    print("=" * 80)
    print("EXECUTIVE PERFORMANCE DASHBOARD & RECOVERY METRICS")
    print("=" * 80)
    print(f"Total Failed Events Analyzed : {summary['total_events_processed']}")
    print(f"Total Failed Volume (INR)    : Rs. {summary['total_failed_volume_inr']:,.2f}")
    print(f"Total Recovered Volume (INR) : Rs. {summary['total_recovered_volume_inr']:,.2f}")
    print(f"Total Intervention Cost      : Rs. {summary['total_intervention_cost_inr']:,.2f}")
    print(f"Net Business Value Added     : Rs. {summary['net_value_added_inr']:,.2f}")
    print(f"Recovery Rate (By Count)     : {summary['recovery_rate_count_pct']}%")
    print(f"Recovery Rate (By Volume)    : {summary['recovery_rate_volume_pct']}%")
    print(f"ROI Multiplier               : {summary['roi_multiplier']}x ROI")
    print("-" * 80)
    
    print("\nINTERVENTION ACTION BREAKDOWN:")
    print(f"{'Action Type':<18} | {'Cases':<6} | {'Recovered':<10} | {'Value Recovered (Rs)':<20} | {'Total Cost (Rs)':<14}")
    print("-" * 75)
    for act in action_breakdown:
        print(f"{act['action']:<18} | {act['total_cases']:<6} | {act['recovered_cases']:<10} | Rs. {act['recovered_val']:<16,.2f} | Rs. {act['total_cost']:<10,.2f}")
        
    print("=" * 80)
    return sim_results

if __name__ == "__main__":
    run_full_pipeline()
