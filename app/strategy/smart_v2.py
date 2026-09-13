"""Auditable Smart v2 scoring primitives.

All returned scores are MXN surplus after the configured reservation-wage
value of time. A non-negative score accepts; a negative score skips. Hard
constraints and deadline feasibility are evaluated before these functions.
"""
from dataclasses import dataclass


def commitment_penalty(commitment_horizon_min: float, free_window_min: float,
                       cost_per_min: float) -> float:
    return max(0.0, commitment_horizon_min - free_window_min) * cost_per_min


def sla_risk_penalty(minimum_margin_min: float | None, preferred_buffer_min: float,
                     cost_per_min: float) -> float:
    if minimum_margin_min is None:
        return 0.0
    if minimum_margin_min < 0:
        return float("inf")
    return max(0.0, preferred_buffer_min - minimum_margin_min) * cost_per_min


def zone_value_mxn(zone_value_mxn_hr: float, time_min: float) -> float:
    return zone_value_mxn_hr * time_min / 60


@dataclass(frozen=True)
class SmartScore:
    mode: str
    final_score: float
    commitment_penalty_mxn: float
    sla_risk_penalty_mxn: float
    required_time_value_mxn: float


def idle_score(*, net_pay_mxn: float, opportunity_cost_mxn: float,
               dropoff_value_mxn: float, service_time_min: float,
               commitment_horizon_min: float, reservation_wage_mxn_hr: float,
               commitment_free_window_min: float,
               commitment_cost_per_min: float) -> SmartScore:
    commitment = commitment_penalty(commitment_horizon_min,
                                    commitment_free_window_min,
                                    commitment_cost_per_min)
    required = reservation_wage_mxn_hr * service_time_min / 60
    final = net_pay_mxn + dropoff_value_mxn - opportunity_cost_mxn - commitment - required
    return SmartScore("idle", final, commitment, 0.0, required)


def batch_score(*, incremental_net_pay_mxn: float,
                incremental_time_min: float,
                minimum_sla_margin_min: float,
                reservation_wage_mxn_hr: float,
                preferred_sla_buffer_min: float,
                sla_risk_cost_per_min: float) -> SmartScore:
    required = reservation_wage_mxn_hr * incremental_time_min / 60
    risk = sla_risk_penalty(minimum_sla_margin_min, preferred_sla_buffer_min,
                            sla_risk_cost_per_min)
    final = incremental_net_pay_mxn - required - risk
    return SmartScore("batching", final, 0.0, risk, required)
