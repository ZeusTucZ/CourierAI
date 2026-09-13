import React from 'react';
import type { AgentState } from '../types';
import { MONTERREY_ZONES } from '../monterreyGeo';
import { MapPin, ChevronRight } from 'lucide-react';

interface CourierSummaryCardsProps {
  baseline: AgentState | null;
  smart: AgentState | null;
  onInspectLastDecision?: () => void;
}

export const CourierSummaryCards: React.FC<CourierSummaryCardsProps> = ({
  baseline,
  smart,
  onInspectLastDecision,
}) => {
  const bZone = baseline?.current_zone ?? 7;
  const sZone = smart?.current_zone ?? 7;

  return (
    <div className="flex flex-col gap-3">
      {/* 1. FirstNearbyOrderBaseline Card */}
      <div className="bg-gray-900/90 border border-blue-900/40 rounded-xl p-3.5 shadow-lg relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-blue-600 to-blue-400" />
        
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 animate-pulse" />
            <span className="font-bold text-xs uppercase tracking-wider text-blue-300">
              FirstNearbyOrderBaseline
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-blue-950/60 border border-blue-800/60 text-blue-300 capitalize">
            {baseline?.status || 'idle'}
          </span>
        </div>

        {/* Core Financial Metric */}
        <div className="flex items-baseline justify-between mb-2.5 pb-2 border-b border-gray-800">
          <div>
            <div className="text-[10px] text-gray-400 uppercase font-semibold">Ganancia Neta</div>
            <div className="text-xl font-bold font-mono text-white">
              ${(baseline?.net_earnings_mxn ?? 0).toFixed(2)} <span className="text-xs text-gray-400">MXN</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-gray-400">Ubicación Actual</div>
            <div className="text-xs font-bold text-blue-300 flex items-center justify-end gap-1">
              <MapPin className="h-3 w-3 text-blue-400" />
              <span>Z{bZone}: {MONTERREY_ZONES[bZone]?.shortName}</span>
            </div>
          </div>
        </div>

        {/* Operational Grid */}
        <div className="grid grid-cols-3 gap-2 text-center text-xs mb-2.5">
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">Completados</span>
            <strong className="text-white font-mono">{baseline?.orders_completed ?? 0}</strong>
          </div>
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">Distancia</span>
            <strong className="text-white font-mono">{(baseline?.distance_traveled_km ?? 0).toFixed(1)} km</strong>
          </div>
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">MXN/km</span>
            <strong className="text-blue-300 font-mono">${(baseline?.mxn_per_km ?? 0).toFixed(1)}</strong>
          </div>
        </div>

        {/* Last Decision */}
        <div className="bg-blue-950/20 border border-blue-900/30 rounded-lg p-2 text-xs flex items-center justify-between">
          <div className="truncate pr-2">
            <span className="text-[10px] text-blue-400 font-bold mr-1.5">ÚLTIMA DECISIÓN:</span>
            <strong className={`font-mono ${baseline?.last_decision.decision === 'ACCEPT' ? 'text-emerald-400' : 'text-gray-400'}`}>
              {baseline?.last_decision.decision || '—'}
            </strong>
            <span className="text-gray-400 text-[10px] ml-1.5 truncate">
              {baseline?.last_decision.reason || 'Sin ofertas'}
            </span>
          </div>
        </div>
      </div>

      {/* 2. SmartAgent Card */}
      <div className="bg-gray-900/90 border border-purple-900/40 rounded-xl p-3.5 shadow-lg relative overflow-hidden">
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-purple-600 to-fuchsia-400" />
        
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-400 animate-pulse" />
            <span className="font-bold text-xs uppercase tracking-wider text-purple-300 flex items-center gap-1">
              <span>SmartAgent</span>
              <span className="text-[9px] bg-purple-950 text-purple-300 border border-purple-700 px-1 py-0.2 rounded">Estratégico</span>
            </span>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-purple-950/60 border border-purple-800/60 text-purple-300 capitalize">
            {smart?.status || 'idle'}
          </span>
        </div>

        {/* Core Financial Metric */}
        <div className="flex items-baseline justify-between mb-2.5 pb-2 border-b border-gray-800">
          <div>
            <div className="text-[10px] text-gray-400 uppercase font-semibold">Ganancia Neta</div>
            <div className="text-xl font-bold font-mono text-purple-200">
              ${(smart?.net_earnings_mxn ?? 0).toFixed(2)} <span className="text-xs text-gray-400">MXN</span>
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-gray-400">Ubicación Actual</div>
            <div className="text-xs font-bold text-purple-300 flex items-center justify-end gap-1">
              <MapPin className="h-3 w-3 text-purple-400" />
              <span>Z{sZone}: {MONTERREY_ZONES[sZone]?.shortName}</span>
            </div>
          </div>
        </div>

        {/* Operational Grid */}
        <div className="grid grid-cols-3 gap-2 text-center text-xs mb-2.5">
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">Completados</span>
            <strong className="text-white font-mono">{smart?.orders_completed ?? 0}</strong>
          </div>
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">Distancia</span>
            <strong className="text-white font-mono">{(smart?.distance_traveled_km ?? 0).toFixed(1)} km</strong>
          </div>
          <div className="bg-gray-950/80 p-2 rounded-lg border border-gray-800/80">
            <span className="text-[10px] text-gray-400 block">MXN/km</span>
            <strong className="text-purple-300 font-mono">${(smart?.mxn_per_km ?? 0).toFixed(1)}</strong>
          </div>
        </div>

        {/* Smart Strategy Variables & Last Decision */}
        <div className="bg-purple-950/20 border border-purple-900/30 rounded-lg p-2 text-xs flex items-center justify-between">
          <div className="truncate pr-2">
            <span className="text-[10px] text-purple-400 font-bold mr-1.5">ÚLTIMA DECISIÓN:</span>
            <strong className={`font-mono ${smart?.last_decision.decision === 'ACCEPT' ? 'text-emerald-400' : 'text-amber-400'}`}>
              {smart?.last_decision.decision || '—'}
            </strong>
            <span className="text-gray-300 text-[10px] ml-1.5 truncate">
              {smart?.last_decision.reason || 'Sin ofertas'}
            </span>
          </div>
          {onInspectLastDecision && smart?.last_decision.decision !== '—' && (
            <button
              onClick={onInspectLastDecision}
              className="text-[10px] font-bold text-purple-300 hover:text-white bg-purple-900/60 hover:bg-purple-800 px-2 py-0.5 rounded flex items-center gap-0.5 transition cursor-pointer whitespace-nowrap"
            >
              <span>Detalle</span>
              <ChevronRight className="h-3 w-3" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
