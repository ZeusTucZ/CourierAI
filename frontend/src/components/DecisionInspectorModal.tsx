import React from 'react';
import { X, CheckCircle2, XCircle, DollarSign } from 'lucide-react';
import type { DecisionInspectorData } from '../types';

interface DecisionInspectorModalProps {
  data: DecisionInspectorData | null;
  onClose: () => void;
}

export const DecisionInspectorModal: React.FC<DecisionInspectorModalProps> = ({ data, onClose }) => {
  if (!data) return null;

  const smart = data.smart;
  const econ = smart.economics;
  const isAccept = smart.decision === 'ACCEPT';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-gray-900 border border-purple-500/40 rounded-2xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl shadow-purple-950/40 p-6 flex flex-col gap-5">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-gray-800 pb-4">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-gray-800 text-purple-300 border border-gray-700">
                {data.order_id}
              </span>
              <span className="text-xs text-gray-400 font-mono">at {data.sim_time}</span>
              <span className="text-xs text-gray-500">({data.offer_details.platform.toUpperCase()})</span>
            </div>
            <h2 className="text-lg font-bold text-white mt-1 m-0">SmartAgent Decision Inspector</h2>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition cursor-pointer"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Primary Decision Banner */}
        <div
          className={`p-4 rounded-xl border flex items-center justify-between ${
            isAccept
              ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
              : 'bg-rose-950/30 border-rose-500/40 text-rose-300'
          }`}
        >
          <div className="flex items-center gap-3">
            {isAccept ? <CheckCircle2 className="h-6 w-6 text-emerald-400" /> : <XCircle className="h-6 w-6 text-rose-400" />}
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider">SMART DECISION</div>
              <div className="text-xl font-bold font-mono">{smart.decision}</div>
            </div>
          </div>

          {smart.binding_constraint && (
            <div className="text-right">
              <span className="text-[10px] uppercase text-gray-400 block font-semibold">Binding Constraint</span>
              <span className="text-xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 px-2 py-0.5 rounded">
                {smart.binding_constraint}
              </span>
            </div>
          )}
        </div>

        {/* Reason Narrative */}
        <div className="bg-gray-950/80 p-3.5 rounded-xl border border-gray-800">
          <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wider block mb-1">
            Official Reason String
          </span>
          <p className="text-xs text-gray-200 leading-relaxed font-mono m-0">
            "{smart.reason}"
          </p>
        </div>

        {/* Economic Drivers Breakdown */}
        <div>
          <span className="text-xs font-bold text-gray-300 uppercase tracking-wider block mb-2 flex items-center gap-1.5">
            <DollarSign className="h-3.5 w-3.5 text-purple-400" />
            <span>Economic Optimization Variables</span>
          </span>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs">
            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Net Pay</span>
              <strong className="text-white font-mono text-sm">
                ${econ.net_pay_mxn !== null ? econ.net_pay_mxn.toFixed(2) : '—'} MXN
              </strong>
              <span className="text-gray-500 text-[10px] block">
                Gross: ${econ.gross_pay_mxn?.toFixed(2) || '0'} - Cost: ${econ.operating_cost_mxn?.toFixed(2) || '0'}
              </span>
            </div>

            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Adjusted Rate (MXN/h)</span>
              <strong className="text-purple-300 font-mono text-sm">
                ${econ.adjusted_rate_mxn_hr !== null ? econ.adjusted_rate_mxn_hr.toFixed(2) : '—'}/h
              </strong>
              <span className="text-gray-500 text-[10px] block">
                Raw: ${econ.raw_rate_mxn_hr?.toFixed(2) || '0'}/h
              </span>
            </div>

            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Reservation Wage</span>
              <strong className="text-white font-mono text-sm">
                ${econ.reservation_wage_mxn_hr !== null ? econ.reservation_wage_mxn_hr.toFixed(2) : '125.00'}/h
              </strong>
              <span className="text-gray-500 text-[10px] block">
                Threshold: 125 MXN/h
              </span>
            </div>

            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Deadhead Distance</span>
              <strong className="text-gray-200 font-mono text-sm">
                {econ.deadhead_km !== null ? `${econ.deadhead_km.toFixed(2)} km` : '0.00 km'}
              </strong>
              <span className="text-gray-500 text-[10px] block">To pickup</span>
            </div>

            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Zone Value Offset</span>
              <strong className="text-gray-200 font-mono text-sm">
                ${econ.zone_value_mxn_hr !== null ? econ.zone_value_mxn_hr.toFixed(2) : '0.00'}
              </strong>
              <span className="text-gray-500 text-[10px] block">Dropoff zone value</span>
            </div>

            <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
              <span className="text-gray-400 block text-[10px] uppercase">Opportunity Cost</span>
              <strong className="text-gray-200 font-mono text-sm">
                ${econ.opportunity_cost_mxn !== null ? econ.opportunity_cost_mxn.toFixed(2) : '0.00'}
              </strong>
              <span className="text-gray-500 text-[10px] block">Expected foregone</span>
            </div>
          </div>
        </div>

        {/* Stacking & Historical Signals if present */}
        {(econ.stacking_impact_min !== null || smart.historical_signal) && (
          <div className="bg-gray-950/40 p-3 rounded-xl border border-gray-800 text-xs space-y-1.5">
            <span className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider block">
              Routing & Demand Model Context
            </span>
            {econ.stacking_impact_min !== null && (
              <div className="flex justify-between text-gray-300 font-mono text-[11px]">
                <span>Stacking Insertion Delay:</span>
                <span>{econ.stacking_impact_min.toFixed(1)} minutes</span>
              </div>
            )}
            {smart.historical_signal && (
              <div className="text-[11px] text-gray-400 font-mono">
                Historical signal (Zone {data.offer_details.zone_pickup}): sample count {smart.historical_signal.sample_count || 'N/A'}, exp distance {smart.historical_signal.expected_trip_distance ? `${smart.historical_signal.expected_trip_distance.toFixed(1)} km` : 'N/A'}.
              </div>
            )}
          </div>
        )}

        {/* Baseline Comparison Section */}
        <div className="pt-3 border-t border-gray-800">
          <div className="flex items-center justify-between bg-blue-950/20 border border-blue-500/20 rounded-xl p-3 text-xs">
            <div>
              <span className="text-[10px] font-semibold text-blue-400 uppercase block">
                How Simple Baseline Decided
              </span>
              <span className="font-bold text-white mt-0.5 block">
                {data.baseline.decision} — {data.baseline.reason}
              </span>
            </div>
            <div className="text-right font-mono text-[11px] text-gray-400">
              Trip: {data.offer_details.distance_total_km} km ≤ {data.baseline.threshold_km} km threshold
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
