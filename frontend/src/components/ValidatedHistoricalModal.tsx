import React from 'react';
import { X, Award } from 'lucide-react';
import type { HistoricalEvaluationData } from '../types';

interface ValidatedHistoricalModalProps {
  isOpen: boolean;
  onClose: () => void;
  data: HistoricalEvaluationData | null;
}

export const ValidatedHistoricalModal: React.FC<ValidatedHistoricalModalProps> = ({ isOpen, onClose, data }) => {
  if (!isOpen) return null;

  const stats = data || {
    evaluation_name: 'Offline held-out evaluation (20 shifts)',
    seed_count: 20,
    aggregate_economics: {
      mean_baseline_net_mxn: 896.73,
      mean_smart_net_mxn: 1041.82,
      mean_improvement_pct: 17.12,
      smart_win_rate_pct: 85.0,
    },
    aggregate_operations: {
      mean_baseline_distance_km: 88.92,
      mean_smart_distance_km: 76.68,
      total_smart_safety_violations: 0,
      total_baseline_safety_violations: 0,
    },
  };

  const econ = stats.aggregate_economics;
  const ops = stats.aggregate_operations;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-gray-900 border border-purple-500/40 rounded-2xl w-full max-w-xl p-6 shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center gap-2">
            <Award className="h-5 w-5 text-purple-400" />
            <div>
              <h2 className="text-base font-bold text-white m-0">Validated Performance</h2>
              <span className="text-[10px] uppercase font-bold text-purple-400 tracking-wider">
                Offline held-out evaluation ({stats.seed_count} shifts)
              </span>
            </div>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-3 bg-purple-950/20 border border-purple-800/40 rounded-xl text-xs text-gray-300">
          <strong className="text-purple-300 block mb-1">Benchmark Certification:</strong>
          These statistical figures represent the official, frozen evaluation over 20 completely new held-out seeds (20001–20020). They are immutable and do not change with interactive demo runs.
        </div>

        {/* 6 Key Verified Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
          <div className="bg-gray-950 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-400 block text-[10px] uppercase">Baseline Mean Net</span>
            <strong className="text-white font-mono text-base block mt-0.5">
              ${econ.mean_baseline_net_mxn.toFixed(2)} MXN
            </strong>
            <span className="text-gray-500 text-[10px]">8-hour shift</span>
          </div>

          <div className="bg-gray-950 p-3 rounded-lg border border-purple-500/30">
            <span className="text-purple-400 block text-[10px] uppercase font-semibold">SmartAgent Mean Net</span>
            <strong className="text-purple-200 font-mono text-base block mt-0.5">
              ${econ.mean_smart_net_mxn.toFixed(2)} MXN
            </strong>
            <span className="text-purple-400/70 text-[10px]">+$145.10 / shift</span>
          </div>

          <div className="bg-gray-950 p-3 rounded-lg border border-emerald-500/30">
            <span className="text-emerald-400 block text-[10px] uppercase font-semibold">Average Uplift</span>
            <strong className="text-emerald-300 font-mono text-base block mt-0.5">
              +{econ.mean_improvement_pct.toFixed(2)}%
            </strong>
            <span className="text-emerald-400/70 text-[10px]">Net profit uplift</span>
          </div>

          <div className="bg-gray-950 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-400 block text-[10px] uppercase">Smart Win Rate</span>
            <strong className="text-white font-mono text-base block mt-0.5">
              {econ.smart_win_rate_pct.toFixed(1)}%
            </strong>
            <span className="text-gray-500 text-[10px]">17 wins / 3 losses</span>
          </div>

          <div className="bg-gray-950 p-3 rounded-lg border border-gray-800">
            <span className="text-gray-400 block text-[10px] uppercase">Distance Efficiency</span>
            <strong className="text-white font-mono text-base block mt-0.5">
              -13.76% km
            </strong>
            <span className="text-gray-500 text-[10px]">
              {ops.mean_smart_distance_km.toFixed(1)} km vs {ops.mean_baseline_distance_km.toFixed(1)} km
            </span>
          </div>

          <div className="bg-gray-950 p-3 rounded-lg border border-emerald-500/30">
            <span className="text-emerald-400 block text-[10px] uppercase font-semibold">Safety Violations</span>
            <strong className="text-emerald-300 font-mono text-base block mt-0.5">
              {ops.total_smart_safety_violations} Violations
            </strong>
            <span className="text-emerald-400/70 text-[10px]">100% hard compliance</span>
          </div>
        </div>

        <div className="pt-2 border-t border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-gray-800 hover:bg-gray-700 text-white rounded-lg text-xs font-semibold transition cursor-pointer"
          >
            Close Benchmark
          </button>
        </div>
      </div>
    </div>
  );
};
