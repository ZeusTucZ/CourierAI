from app.models.responses import Economics


def economic_reason(accepted: bool, economics: Economics) -> str:
    action = "Accepted" if accepted else "Skipped"
    comparison = "meets or exceeds" if accepted else "is below"
    rate = economics.adjusted_rate_mxn_hr
    wage = economics.reservation_wage_mxn_hr
    rate_text, wage_text = f"{rate:.2f}", f"{wage:.2f}"
    if rate != wage and rate_text == wage_text:
        # Preserve visible differences at thresholds without cluttering ordinary reasons.
        rate_text, wage_text = repr(rate), repr(wage)
    detail = "including zone value, opportunity cost and skip penalty." if economics.opportunity_cost_mxn or economics.skip_penalty_mxn else "including dropoff zone value."
    return (f"{action}: adjusted rate MXN {rate_text}/hr "
            f"{comparison} reservation_wage MXN {wage_text}/hr, "
            f"{detail}")
