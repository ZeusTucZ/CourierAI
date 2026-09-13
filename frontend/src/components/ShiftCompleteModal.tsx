import React from 'react';
import { Trophy, RotateCcw } from 'lucide-react';
import type { SimulationState } from '../types';

interface ShiftCompleteModalProps {
  isOpen: boolean;
  state: SimulationState | null;
  onReset: () => void;
  onClose: () => void;
}

export const ShiftCompleteModal: React.FC<ShiftCompleteModalProps> = ({ isOpen, state, onReset, onClose }) => {
  if (!isOpen || !state) return null;

  const b = state.baseline;
  const s = state.smart;
  const diff = state.comparison.net_difference;
  const uplift = state.comparison.uplift_pct;
  const isSmartWinner = s.net_earnings_mxn > b.net_earnings_mxn;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-in fade-in duration-300">
      <div className="bg-gray-900 border border-purple-500/50 rounded-2xl w-full max-w-lg p-6 shadow-2xl flex flex-col gap-5 text-center">
        <div className="flex flex-col items-center">
          <div className="w-12 h-12 rounded-full bg-purple-500/20 border border-purple-500/40 flex items-center justify-center mb-2">
            <Trophy className="h-6 w-6 text-amber-400" />
          </div>
          <h2 className="text-xl font-extrabold text-white m-0">SHIFT COMPLETE</h2>
          <span className="text-xs text-gray-400 mt-1 font-mono">
            8 Simulated Hours Evaluated | Seed {state.seed}
          </span>
        </div>

        {/* Winner Announcement Banner */}
        <div className="bg-gradient-to-r from-purple-950/40 via-purple-900/40 to-purple-950/40 border border-purple-500/30 rounded-xl p-4">
          <div className="text-xs font-bold text-purple-300 uppercase tracking-wider mb-1">
            {isSmartWinner ? 'SMARTAGENT WON BY' : 'BASELINE WON BY'}
          </div>
          <div className="text-3xl font-black font-mono text-emerald-400">
            +${Math.abs(diff).toFixed(2)} MXN
          </div>
          <div className="text-sm font-bold text-emerald-300 mt-0.5 font-mono">
            +{Math.abs(uplift).toFixed(1)}% Uplift
          </div>
        </div>

        {/* Side by side comparison */}
        <div className="grid grid-cols-2 gap-3 text-xs text-left">
          {/* Baseline summary */}
          <div className="bg-gray-950 p-3.5 rounded-xl border border-gray-800">
            <div className="font-bold text-blue-400 text-[11px] uppercase mb-2">
              FirstNearbyOrderBaseline
            </div>
            <div className="space-y-1.5 font-mono">
              <div className="flex justify-between">
                <span className="text-gray-400">Net:</span>
                <strong className="text-white">${b.net_earnings_mxn.toFixed(2)}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Orders:</span>
                <span className="text-gray-200">{b.orders_completed}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Distance:</span>
                <span className="text-gray-200">{b.distance_traveled_km.toFixed(1)} km</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">MXN / km:</span>
                <span className="text-gray-200">${b.mxn_per_km.toFixed(1)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Late:</span>
                <span className="text-gray-200">{b.late_deliveries}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Safety:</span>
                <span className="text-emerald-400">0 violations</span>
              </div>
            </div>
          </div>

          {/* Smart summary */}
          <div className="bg-gray-950 p-3.5 rounded-xl border border-purple-500/30">
            <div className="font-bold text-purple-400 text-[11px] uppercase mb-2">
              SmartAgent
            </div>
            <div className="space-y-1.5 font-mono">
              <div className="flex justify-between">
                <span className="text-purple-300 font-semibold">Net:</span>
                <strong className="text-emerald-400">${s.net_earnings_mxn.toFixed(2)}</strong>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Orders:</span>
                <span className="text-gray-200">{s.orders_completed}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Distance:</span>
                <span className="text-gray-200">{s.distance_traveled_km.toFixed(1)} km</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">MXN / km:</span>
                <span className="text-emerald-300 font-bold">${s.mxn_per_km.toFixed(1)}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Late:</span>
                <span className="text-gray-200">{s.late_deliveries}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-gray-400">Safety:</span>
                <span className="text-emerald-400">0 violations</span>
              </div>
            </div>
          </div>
        </div>

        {/* Buttons */}
        <div className="pt-2 flex gap-2">
          <button
            onClick={onClose}
            className="flex-1 py-2 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs font-semibold transition cursor-pointer"
          >
            Review Simulation View
          </button>
          <button
            onClick={() => {
              onClose();
              onReset();
            }}
            className="flex-1 py-2 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-bold transition flex items-center justify-center gap-1.5 cursor-pointer shadow-lg"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Reset & New Run</span>
          </button>
        </div>
      </div>
    </div>
  );
};
