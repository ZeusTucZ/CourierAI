import React from 'react';
import type { SimulationState } from '../types';
import { Trophy, RotateCcw, X, ShieldCheck } from 'lucide-react';

interface SimpleShiftCompleteModalProps {
  isOpen: boolean;
  state: SimulationState | null;
  onReset: () => void;
  onClose: () => void;
}

export const SimpleShiftCompleteModal: React.FC<SimpleShiftCompleteModalProps> = ({
  isOpen,
  state,
  onReset,
  onClose,
}) => {
  if (!isOpen || !state) return null;

  const b = state.baseline;
  const s = state.smart;
  const diff = s.net_earnings_mxn - b.net_earnings_mxn;
  const uplift = b.net_earnings_mxn > 0 ? (diff / b.net_earnings_mxn) * 100 : 0;
  const isSmartWinner = s.net_earnings_mxn > b.net_earnings_mxn;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-xs animate-in fade-in duration-150">
      <div className="bg-white border border-slate-200 rounded-2xl w-full max-w-lg p-6 shadow-xl flex flex-col gap-4 text-slate-800">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 pb-3">
          <div className="flex items-center gap-2">
            <Trophy className="h-6 w-6 text-amber-500" />
            <h2 className="text-lg font-extrabold text-slate-900 m-0">
              SHIFT COMPLETE
            </h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 text-slate-400 hover:text-slate-700 rounded-lg transition cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Winner Announcement */}
        <div className="p-3 bg-sky-50 border border-sky-200 rounded-xl text-center">
          <span className="text-xs uppercase font-bold text-sky-700 block tracking-wider">
            Winner
          </span>
          <strong className="text-xl font-bold text-sky-900 block my-0.5">
            {isSmartWinner ? 'SmartAgent' : 'FirstNearbyOrderBaseline'}
          </strong>
          <span className="text-xs font-semibold text-emerald-700">
            {isSmartWinner
              ? `Smart won by +$${diff.toFixed(2)} MXN (+${uplift.toFixed(1)}%)`
              : `Baseline finished ahead by +$${Math.abs(diff).toFixed(2)} MXN`}
          </span>
        </div>

        {/* Head-to-Head Comparison */}
        <div className="grid grid-cols-2 gap-3 text-xs">
          {/* Baseline */}
          <div className="bg-slate-50 border border-slate-200 p-3 rounded-xl">
            <span className="text-[10px] uppercase font-bold text-slate-400 block mb-1">
              Simple Baseline
            </span>
            <div className="font-mono text-lg font-bold text-slate-900 mb-2">
              ${b.net_earnings_mxn.toFixed(2)} MXN
            </div>
            <div className="space-y-1 text-slate-600">
              <div>Orders completed: <strong>{b.orders_completed}</strong></div>
              <div>Distance: <strong>{b.distance_traveled_km.toFixed(1)} km</strong></div>
              <div>Safety violations: <strong>{b.safety_violations}</strong></div>
            </div>
          </div>

          {/* Smart */}
          <div className="bg-sky-50/50 border border-sky-200 p-3 rounded-xl">
            <span className="text-[10px] uppercase font-bold text-sky-700 block mb-1">
              Smart Agent
            </span>
            <div className="font-mono text-lg font-bold text-sky-900 mb-2">
              ${s.net_earnings_mxn.toFixed(2)} MXN
            </div>
            <div className="space-y-1 text-slate-700">
              <div>Orders completed: <strong>{s.orders_completed}</strong></div>
              <div>Distance: <strong>{s.distance_traveled_km.toFixed(1)} km</strong></div>
              <div>Safety violations: <strong>{s.safety_violations}</strong></div>
            </div>
          </div>
        </div>

        {/* Section 38: Offline Validated Results */}
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 text-xs">
          <div className="flex items-center gap-1.5 font-bold text-slate-700 mb-1.5">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            <span>Validated Offline Results (20 Held-Out Shifts)</span>
          </div>
          <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-400 block text-[10px]">Average Uplift</span>
              <strong className="text-emerald-700 font-bold">+17.12%</strong>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-400 block text-[10px]">Smart Win Rate</span>
              <strong className="text-slate-900 font-bold">85.0% (17/20)</strong>
            </div>
            <div className="bg-white p-2 rounded border border-slate-200">
              <span className="text-slate-400 block text-[10px]">Safety Violations</span>
              <strong className="text-emerald-700 font-bold">0 Violations</strong>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex justify-end gap-2 pt-2 border-t border-slate-100">
          <button
            onClick={onReset}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 hover:bg-slate-200 text-slate-700 font-semibold rounded-lg text-xs transition cursor-pointer"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>New Shift</span>
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-slate-900 hover:bg-slate-800 text-white font-semibold rounded-lg text-xs transition cursor-pointer"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
