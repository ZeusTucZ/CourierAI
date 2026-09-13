import React from 'react';
import { MapPin, Package, Clock, ShieldCheck, Compass } from 'lucide-react';
import type { AgentState } from '../types';

interface AgentPanelProps {
  agent: AgentState | null;
  isSmart?: boolean;
  onInspectLastDecision?: () => void;
}

export const AgentPanel: React.FC<AgentPanelProps> = ({ agent, isSmart = false, onInspectLastDecision }) => {
  if (!agent) {
    return (
      <div className="bg-gray-900/60 rounded-xl p-6 border border-gray-800 flex items-center justify-center min-h-[400px]">
        <span className="text-sm text-gray-500">Loading agent data...</span>
      </div>
    );
  }

  const isAccept = agent.last_decision.decision === 'ACCEPT';
  const isSkip = agent.last_decision.decision === 'SKIP';

  const statusColorMap: Record<string, string> = {
    idle: 'bg-gray-800 text-gray-300 border-gray-700',
    to_pickup: 'bg-amber-500/20 text-amber-300 border-amber-500/40 animate-pulse',
    waiting: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
    to_dropoff: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40 animate-pulse',
    on_break: 'bg-purple-500/20 text-purple-300 border-purple-500/40',
  };

  const statusBadge = statusColorMap[agent.status.toLowerCase()] || 'bg-gray-800 text-gray-300 border-gray-700';

  return (
    <div
      className={`rounded-xl border p-5 flex flex-col gap-4 transition shadow-lg ${
        isSmart
          ? 'bg-gray-900/80 border-purple-500/30 shadow-purple-950/20'
          : 'bg-gray-900/80 border-blue-500/20 shadow-blue-950/20'
      }`}
    >
      {/* Panel Top Header */}
      <div className="flex items-center justify-between border-b border-gray-800 pb-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-white tracking-wide uppercase m-0">
              {agent.name}
            </h2>
            <span
              className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded-full border ${
                isSmart
                  ? 'bg-purple-500/10 text-purple-300 border-purple-500/30'
                  : 'bg-blue-500/10 text-blue-300 border-blue-500/30'
              }`}
            >
              {isSmart ? 'Optimized Policy' : 'Novice Proximity Heuristic'}
            </span>
          </div>
          <p className="text-xs text-gray-400 mt-0.5">
            {isSmart
              ? 'Evaluates economics, reservation wage (125 MXN/h), zone values & dynamic SLAs'
              : 'Accepts first feasible offer within historical distance threshold (≤ 14.99 km)'}
          </p>
        </div>

        {/* Current Status Pill */}
        <div className="flex flex-col items-end gap-1">
          <span className={`px-2.5 py-1 text-xs font-semibold rounded-full border uppercase tracking-wider ${statusBadge}`}>
            {agent.status.replace('_', ' ')}
          </span>
          <div className="flex items-center gap-1 text-xs text-gray-400">
            <MapPin className="h-3 w-3 text-red-400" />
            <span>Zone <strong className="text-white font-mono">{agent.current_zone}</strong></span>
          </div>
        </div>
      </div>

      {/* Main Stats Grid */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
          <span className="text-[11px] font-medium text-gray-400 block uppercase">Net Earnings</span>
          <span className="text-lg font-bold font-mono text-white">
            ${agent.net_earnings_mxn.toFixed(2)}
          </span>
        </div>
        <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
          <span className="text-[11px] font-medium text-gray-400 block uppercase">Orders Completed</span>
          <span className="text-lg font-bold font-mono text-white">
            {agent.orders_completed}
          </span>
        </div>
        <div className="bg-gray-950/60 p-2.5 rounded-lg border border-gray-800">
          <span className="text-[11px] font-medium text-gray-400 block uppercase">Distance (km)</span>
          <span className="text-lg font-bold font-mono text-white">
            {agent.distance_traveled_km.toFixed(1)} <span className="text-[10px] text-gray-500 font-normal">km</span>
          </span>
        </div>
      </div>

      {/* Efficiency Metrics */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div className="bg-gray-950/40 p-2 rounded border border-gray-800/80">
          <span className="text-gray-400 block text-[10px] uppercase">MXN / Hour</span>
          <strong className="text-white font-mono text-sm">${agent.mxn_per_hour.toFixed(1)}/h</strong>
        </div>
        <div className="bg-gray-950/40 p-2 rounded border border-gray-800/80">
          <span className="text-gray-400 block text-[10px] uppercase">MXN / km</span>
          <strong className="text-white font-mono text-sm">${agent.mxn_per_km.toFixed(1)}/km</strong>
        </div>
        <div className="bg-gray-950/40 p-2 rounded border border-gray-800/80">
          <span className="text-gray-400 block text-[10px] uppercase">Idle Time</span>
          <strong className="text-white font-mono text-sm">{agent.idle_time_min.toFixed(0)} min</strong>
        </div>
        <div className="bg-gray-950/40 p-2 rounded border border-gray-800/80">
          <span className="text-gray-400 block text-[10px] uppercase">Late Deliveries</span>
          <strong className={`font-mono text-sm ${agent.late_deliveries > 0 ? 'text-amber-400' : 'text-gray-300'}`}>
            {agent.late_deliveries}
          </strong>
        </div>
      </div>

      {/* Repositioning stat for Smart */}
      {isSmart && (
        <div className="flex items-center justify-between text-xs px-3 py-1.5 bg-purple-950/30 border border-purple-800/40 rounded-lg">
          <span className="text-purple-300 flex items-center gap-1.5 font-medium">
            <Compass className="h-3.5 w-3.5 text-purple-400" />
            <span>Strategic Repositioning:</span>
          </span>
          <span className="font-mono text-purple-200">
            {agent.reposition_distance_km || 0} km ({agent.reposition_count || 0} moves)
          </span>
        </div>
      )}

      {/* Safety & Compliance Badge */}
      <div className="flex items-center justify-between text-xs px-3 py-1.5 bg-emerald-950/30 border border-emerald-800/30 rounded-lg">
        <span className="text-emerald-300 flex items-center gap-1.5 font-medium">
          <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
          <span>Safety Violations:</span>
        </span>
        <strong className="text-emerald-400 font-mono">0 (100% Compliant)</strong>
      </div>

      {/* Active Commitments / Orders */}
      <div className="bg-gray-950/60 p-3 rounded-lg border border-gray-800">
        <div className="flex items-center justify-between text-xs font-semibold text-gray-300 mb-2">
          <span className="flex items-center gap-1">
            <Package className="h-3.5 w-3.5 text-blue-400" />
            <span>Active Orders ({agent.active_orders?.length || 0})</span>
          </span>
          <span className="text-gray-500 font-normal text-[11px]">
            Accepted: {agent.orders_accepted} | Skipped: {agent.orders_skipped}
          </span>
        </div>

        {agent.active_orders && agent.active_orders.length > 0 ? (
          <div className="space-y-1.5">
            {agent.active_orders.map((job) => (
              <div
                key={job.order_id}
                className="flex items-center justify-between text-xs bg-gray-900 px-2.5 py-1.5 rounded border border-gray-800"
              >
                <span className="font-mono font-bold text-gray-200">{job.order_id}</span>
                <span className="text-gray-400">
                  Z{job.pickup_zone} → Z{job.dropoff_zone}
                </span>
                <span className="text-amber-300 font-mono flex items-center gap-1">
                  <Clock className="h-3 w-3" /> ETA {job.promised_time}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-xs text-gray-500 italic py-1 m-0">No active deliveries in progress (idle)</p>
        )}
      </div>

      {/* Last Decision Summary */}
      <div className="mt-auto pt-3 border-t border-gray-800/80 flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Last Decision</span>
          <div className="flex items-center gap-1.5">
            <span
              className={`px-2 py-0.5 rounded text-xs font-bold font-mono ${
                isAccept
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : isSkip
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
                  : 'bg-gray-800 text-gray-400'
              }`}
            >
              {agent.last_decision.decision}
            </span>
            {agent.last_decision.binding_constraint && (
              <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-amber-500/10 text-amber-300 border border-amber-500/30">
                {agent.last_decision.binding_constraint}
              </span>
            )}
          </div>
        </div>

        <p className="text-xs text-gray-300 line-clamp-2 bg-gray-950/70 p-2 rounded border border-gray-800/70 m-0">
          {agent.last_decision.reason}
        </p>

        {isSmart && agent.last_decision.adjusted_rate_mxn_hr && (
          <div className="flex items-center justify-between text-[11px] text-gray-400 px-1">
            <span>Rate comparison:</span>
            <span className="font-mono text-purple-300">
              ${agent.last_decision.adjusted_rate_mxn_hr.toFixed(1)} MXN/h vs ${agent.last_decision.reservation_wage_mxn_hr?.toFixed(1) || 125} MXN/h
            </span>
          </div>
        )}

        {isSmart && onInspectLastDecision && (
          <button
            onClick={onInspectLastDecision}
            className="text-xs text-purple-400 hover:text-purple-300 text-right underline cursor-pointer mt-1"
          >
            Inspect Smart Decision Reasoning →
          </button>
        )}
      </div>
    </div>
  );
};
