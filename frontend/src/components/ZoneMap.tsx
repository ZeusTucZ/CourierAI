import React from 'react';
import { Navigation } from 'lucide-react';
import type { AgentState, IncomingOrderInfo } from '../types';

interface ZoneMapProps {
  baseline: AgentState | null;
  smart: AgentState | null;
  incomingOrder: IncomingOrderInfo | null;
}

export const ZoneMap: React.FC<ZoneMapProps> = ({ baseline, smart, incomingOrder }) => {
  const bZone = baseline?.current_zone || 7;
  const sZone = smart?.current_zone || 7;
  const pZone = incomingOrder?.zone_pickup;
  const dZone = incomingOrder?.zone_dropoff;

  // 12 Zones grid (3 rows x 4 columns)
  const zones = Array.from({ length: 12 }, (_, i) => i + 1);

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-gray-800 pb-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-200 flex items-center gap-1.5 m-0">
          <Navigation className="h-4 w-4 text-purple-400" />
          <span>Zone Spatial State (12 Zones Grid)</span>
        </h3>
        <div className="flex items-center gap-3 text-[11px]">
          <span className="flex items-center gap-1 text-blue-400 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block"></span>
            Baseline (Z{bZone})
          </span>
          <span className="flex items-center gap-1 text-purple-400 font-medium">
            <span className="w-2.5 h-2.5 rounded-full bg-purple-500 inline-block"></span>
            Smart (Z{sZone})
          </span>
          {pZone && (
            <span className="flex items-center gap-1 text-emerald-400 font-medium">
              <span className="w-2 h-2 rounded bg-emerald-500 inline-block"></span>
              Pickup (Z{pZone})
            </span>
          )}
          {dZone && (
            <span className="flex items-center gap-1 text-amber-400 font-medium">
              <span className="w-2 h-2 rounded bg-amber-500 inline-block"></span>
              Dropoff (Z{dZone})
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2.5">
        {zones.map((z) => {
          const hasBase = bZone === z;
          const hasSmart = sZone === z;
          const isPickup = pZone === z;
          const isDropoff = dZone === z;
          const isFlagged = z === 11; // Flagged night zone

          let cellBg = 'bg-gray-950/70 border-gray-800';
          if (isPickup) cellBg = 'bg-emerald-950/40 border-emerald-500/50';
          if (isDropoff) cellBg = 'bg-amber-950/40 border-amber-500/50';

          return (
            <div
              key={z}
              className={`p-2.5 rounded-lg border transition-all duration-200 flex flex-col justify-between min-h-[72px] relative overflow-hidden ${cellBg}`}
            >
              <div className="flex items-center justify-between">
                <span className="text-xs font-mono font-bold text-gray-300">
                  Zone {z}
                </span>
                {isFlagged && (
                  <span className="text-[9px] uppercase font-bold text-red-400 bg-red-950/60 px-1 rounded border border-red-900/60" title="High risk night zone">
                    Flagged
                  </span>
                )}
              </div>

              {/* Courier Markers in this zone */}
              <div className="flex flex-wrap gap-1 mt-1.5 items-center">
                {hasBase && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-blue-600 text-white shadow">
                    <span>B</span>
                    <span className="text-[9px] opacity-80">({baseline?.status.substring(0, 4)})</span>
                  </span>
                )}
                {hasSmart && (
                  <span className="inline-flex items-center gap-1 text-[10px] font-bold font-mono px-1.5 py-0.5 rounded bg-purple-600 text-white shadow animate-pulse">
                    <span>S</span>
                    <span className="text-[9px] opacity-80">({smart?.status.substring(0, 4)})</span>
                  </span>
                )}
              </div>

              {/* Order target tags */}
              <div className="flex gap-1 mt-1">
                {isPickup && (
                  <span className="text-[9px] font-bold px-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                    PICKUP
                  </span>
                )}
                {isDropoff && (
                  <span className="text-[9px] font-bold px-1 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                    DROPOFF
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
