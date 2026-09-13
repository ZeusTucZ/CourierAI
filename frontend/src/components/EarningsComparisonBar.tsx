import React from 'react';
import { TrendingUp, ArrowUpRight, Trophy } from 'lucide-react';
import type { SimulationState } from '../types';

interface EarningsComparisonBarProps {
  state: SimulationState | null;
}

export const EarningsComparisonBar: React.FC<EarningsComparisonBarProps> = ({ state }) => {
  const bNet = state?.baseline.net_earnings_mxn ?? 0;
  const sNet = state?.smart.net_earnings_mxn ?? 0;
  const diff = state?.comparison.net_difference ?? (sNet - bNet);
  const uplift = state?.comparison.uplift_pct ?? 0;
  const isSmartWinning = sNet > bNet;
  const isCompleted = state?.status === 'completed';

  const total = Math.max(1, (bNet > 0 ? bNet : 0) + (sNet > 0 ? sNet : 0));
  const bPercent = Math.round(((bNet > 0 ? bNet : 0) / total) * 100);
  const sPercent = 100 - bPercent;

  return (
    <div className="bg-gradient-to-r from-gray-900 via-gray-950 to-gray-900 border-b border-gray-800 px-6 py-4">
      <div className="max-w-7xl mx-auto">
        <div className="grid grid-cols-1 md:grid-cols-3 items-center gap-4">
          {/* Baseline Earnings Card */}
          <div className="bg-gray-900/80 border border-blue-500/20 rounded-xl p-4 flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-blue-400 mb-1 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-400"></span>
                FirstNearbyOrderBaseline
              </div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-white">
                ${bNet.toFixed(2)} <span className="text-xs font-normal text-gray-400">MXN</span>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Gross: ${state?.baseline.gross_earnings_mxn.toFixed(2) || '0.00'} | Costs: ${state?.baseline.operating_costs_mxn.toFixed(2) || '0.00'}
              </div>
            </div>
            <div className="text-right">
              <span className="text-xs font-mono text-gray-400">
                {state?.baseline.orders_completed || 0} completed
              </span>
            </div>
          </div>

          {/* Central Comparison & Uplift Badge */}
          <div className="flex flex-col items-center justify-center text-center px-2 py-1">
            <div className="flex items-center gap-2 mb-1">
              {isCompleted ? (
                <span className="inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
                  <Trophy className="h-3.5 w-3.5 text-amber-400" />
                  <span>WINNER: {isSmartWinning ? 'SMART AGENT' : 'BASELINE'}</span>
                </span>
              ) : (
                <span className="text-xs font-semibold text-gray-400 flex items-center gap-1">
                  <TrendingUp className="h-3.5 w-3.5 text-purple-400" />
                  <span>LIVE SPREAD</span>
                </span>
              )}
            </div>

            <div className="flex items-baseline gap-2">
              <span
                className={`text-2xl sm:text-3xl font-extrabold font-mono tracking-tight ${
                  diff > 0 ? 'text-emerald-400' : diff < 0 ? 'text-rose-400' : 'text-gray-300'
                }`}
              >
                {diff >= 0 ? `+$${diff.toFixed(2)}` : `-$${Math.abs(diff).toFixed(2)}`}
              </span>
              <span className="text-xs text-gray-400 font-mono">MXN</span>
            </div>

            <div className="mt-1 flex items-center gap-1.5">
              <span
                className={`inline-flex items-center text-xs font-bold px-2 py-0.5 rounded-full ${
                  uplift > 0
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : uplift < 0
                    ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    : 'bg-gray-800 text-gray-400'
                }`}
              >
                <ArrowUpRight className="h-3.5 w-3.5" />
                <span>{uplift >= 0 ? `+${uplift.toFixed(1)}%` : `${uplift.toFixed(1)}%`} Smart Uplift</span>
              </span>
            </div>

            {/* Visual ratio bar */}
            <div className="w-full max-w-xs bg-gray-800 h-1.5 rounded-full mt-3 overflow-hidden flex">
              <div
                className="bg-blue-500 transition-all duration-300"
                style={{ width: `${bPercent}%` }}
                title={`Baseline Share: ${bPercent}%`}
              />
              <div
                className="bg-purple-500 transition-all duration-300"
                style={{ width: `${sPercent}%` }}
                title={`SmartAgent Share: ${sPercent}%`}
              />
            </div>
          </div>

          {/* SmartAgent Earnings Card */}
          <div className="bg-gray-900/80 border border-purple-500/30 rounded-xl p-4 flex items-center justify-between shadow-lg shadow-purple-950/20">
            <div>
              <div className="text-xs font-semibold uppercase tracking-wider text-purple-400 mb-1 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-purple-400 animate-pulse"></span>
                SmartAgent
              </div>
              <div className="text-2xl sm:text-3xl font-bold font-mono text-purple-200">
                ${sNet.toFixed(2)} <span className="text-xs font-normal text-gray-400">MXN</span>
              </div>
              <div className="text-xs text-gray-400 mt-1">
                Gross: ${state?.smart.gross_earnings_mxn.toFixed(2) || '0.00'} | Costs: ${state?.smart.operating_costs_mxn.toFixed(2) || '0.00'}
              </div>
            </div>
            <div className="text-right">
              <span className="text-xs font-mono text-purple-300">
                {state?.smart.orders_completed || 0} completed
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
