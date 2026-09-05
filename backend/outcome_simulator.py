"""
Probabilistic Payment Recovery Outcome Simulator & Business Metrics Engine
Simulates realistic customer response behaviors post-intervention to calculate recovered revenue,
operational costs, recovery rates, and net business ROI.
"""

from typing import Dict, Any, List
import random
import pandas as pd

class OutcomeSimulator:
    
    # Base Probabilities and Costs per Intervention
    BENCHMARKS = {
        "AUTO_RETRY": {"base_prob": 0.60, "cost_inr": 0.00},
        "NUDGE_WHATSAPP": {"base_prob": 0.35, "cost_inr": 0.50},
        "NUDGE_SMS": {"base_prob": 0.22, "cost_inr": 0.15},
        "NUDGE_EMAIL": {"base_prob": 0.28, "cost_inr": 0.05},
        "VOICE_CALL": {"base_prob": 0.52, "cost_inr": 3.50},
        "ESCALATE_HUMAN": {"base_prob": 0.40, "cost_inr": 25.00},
        "NO_ACTION_STOP": {"base_prob": 0.00, "cost_inr": 0.00}
    }
    
    @classmethod
    def simulate_event_outcome(cls, event_state: Dict[str, Any], seed: int = None) -> Dict[str, Any]:
        if seed is not None:
            random.seed(seed)
            
        action = event_state.get("action", "NO_ACTION_STOP")
        amount = event_state.get("amount_inr", 0.0)
        recoverability = event_state.get("recoverability_score", 0.50)
        prior_attempts = event_state.get("prior_attempts", 0)
        
        bench = cls.BENCHMARKS.get(action, {"base_prob": 0.0, "cost_inr": 0.0})
        base_prob = bench["base_prob"]
        cost = bench["cost_inr"]
        
        if action == "NO_ACTION_STOP":
            return {
                "outcome_status": "UNRECOVERED_STOPPED",
                "is_recovered": False,
                "amount_recovered_inr": 0.0,
                "intervention_cost_inr": 0.0,
                "net_gain_inr": 0.0,
                "recovery_probability": 0.0
            }
            
        # Adjust probability dynamically based on state
        adjusted_prob = base_prob * (0.5 + recoverability)
        if prior_attempts > 0:
            adjusted_prob *= (1.0 - (prior_attempts * 0.15))
            
        adjusted_prob = max(0.01, min(0.95, round(adjusted_prob, 3)))
        
        # Roll random recovery determination
        is_recovered = random.random() <= adjusted_prob
        recovered_amount = amount if is_recovered else 0.0
        net_gain = recovered_amount - cost
        
        outcome_status = "RECOVERED_SUCCESS" if is_recovered else "FAILED_TO_RECOVER"
        
        return {
            "outcome_status": outcome_status,
            "is_recovered": is_recovered,
            "amount_recovered_inr": recovered_amount,
            "intervention_cost_inr": cost,
            "net_gain_inr": net_gain,
            "recovery_probability": adjusted_prob
        }
        
    @classmethod
    def run_simulation_suite(cls, dataset_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Runs full outcome simulation on processed dataset and computes executive metrics."""
        simulated_records = []
        
        for idx, item in enumerate(dataset_results):
            outcome = cls.simulate_event_outcome(item, seed=idx + 100)
            merged = {**item, **outcome}
            simulated_records.append(merged)
            
        df = pd.DataFrame(simulated_records)
        
        total_events = len(df)
        total_failed_val = df["amount_inr"].sum()
        total_recovered_val = df["amount_recovered_inr"].sum()
        total_cost = df["intervention_cost_inr"].sum()
        net_recovered_val = total_recovered_val - total_cost
        
        recovered_count = df["is_recovered"].sum()
        recovery_rate_pct = (recovered_count / total_events * 100) if total_events > 0 else 0
        volume_recovery_pct = (total_recovered_val / total_failed_val * 100) if total_failed_val > 0 else 0
        
        roi_multiplier = (net_recovered_val / total_cost) if total_cost > 0 else 0
        
        action_breakdown = df.groupby("action").agg(
            total_cases=("event_id", "count"),
            recovered_cases=("is_recovered", "sum"),
            recovered_val=("amount_recovered_inr", "sum"),
            total_cost=("intervention_cost_inr", "sum")
        ).reset_index().to_dict(orient="records")
        
        return {
            "summary_metrics": {
                "total_events_processed": total_events,
                "total_failed_volume_inr": round(total_failed_val, 2),
                "total_recovered_volume_inr": round(total_recovered_val, 2),
                "total_intervention_cost_inr": round(total_cost, 2),
                "net_value_added_inr": round(net_recovered_val, 2),
                "recovery_rate_count_pct": round(recovery_rate_pct, 2),
                "recovery_rate_volume_pct": round(volume_recovery_pct, 2),
                "roi_multiplier": round(roi_multiplier, 1)
            },
            "action_breakdown": action_breakdown,
            "detailed_records": simulated_records
        }

if __name__ == "__main__":
    print("Outcome simulator module initialized.")
