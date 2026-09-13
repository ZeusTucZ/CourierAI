import React, { useState } from 'react';
import { CloudRain, TrendingUp, AlertTriangle, Clock, Zap } from 'lucide-react';
import type { ShockReactionInfo } from '../types';

interface ShockControlsProps {
  onInjectShock: (params: {
    shock_type: 'rain' | 'surge' | 'closure' | 'delay';
    duration_min?: number;
    zone?: number;
    multiplier?: number;
    road?: string;
    slip_min?: number;
  }) => void;
  latestReaction: ShockReactionInfo | null;
}

export const ShockControls: React.FC<ShockControlsProps> = ({ onInjectShock, latestReaction }) => {
  const [selectedRainDuration, setSelectedRainDuration] = useState<number>(30);
  const [surgeZone, setSurgeZone] = useState<number>(3);
  const [surgeMultiplier, setSurgeMultiplier] = useState<number>(1.5);
  const [closureZone, setClosureZone] = useState<number>(7);
  const [delayMinutes, setDelayMinutes] = useState<number>(15);

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-gray-800 pb-2.5">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-200 flex items-center gap-1.5 m-0">
          <Zap className="h-4 w-4 text-amber-400" />
          <span>Inject Exogenous Shocks</span>
        </h3>
        <span className="text-[11px] text-gray-500 font-mono">Applies to both agents identically</span>
      </div>

      {/* Grid of Shock Injection Controls */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3 text-xs">
        {/* Rain Shock */}
        <div className="bg-gray-950/70 p-3 rounded-lg border border-gray-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-1.5 font-bold text-blue-400 mb-1.5">
              <CloudRain className="h-4 w-4" />
              <span>Rain Event</span>
            </div>
            <p className="text-[11px] text-gray-400 mb-2">Increases travel times by 25% across all zones.</p>
            <div className="flex gap-1 mb-3">
              {[15, 30, 45, 60].map((dur) => (
                <button
                  key={dur}
                  onClick={() => setSelectedRainDuration(dur)}
                  className={`flex-1 py-1 text-[10px] font-mono font-semibold rounded ${
                    selectedRainDuration === dur
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  } transition cursor-pointer`}
                >
                  {dur}m
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => onInjectShock({ shock_type: 'rain', duration_min: selectedRainDuration })}
            className="w-full py-1.5 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded text-xs transition cursor-pointer"
          >
            Inject Rain ({selectedRainDuration}m)
          </button>
        </div>

        {/* Surge Shock */}
        <div className="bg-gray-950/70 p-3 rounded-lg border border-gray-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-1.5 font-bold text-amber-400 mb-1.5">
              <TrendingUp className="h-4 w-4" />
              <span>Demand Surge</span>
            </div>
            <p className="text-[11px] text-gray-400 mb-2">Multiplier on base pay in selected zone.</p>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <div>
                <label className="text-[10px] text-gray-500 block">Zone</label>
                <select
                  value={surgeZone}
                  onChange={(e) => setSurgeZone(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 text-white rounded px-1.5 py-0.5 text-xs font-mono"
                >
                  {Array.from({ length: 12 }, (_, i) => i + 1).map((z) => (
                    <option key={z} value={z}>Zone {z}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] text-gray-500 block">Mult</label>
                <select
                  value={surgeMultiplier}
                  onChange={(e) => setSurgeMultiplier(Number(e.target.value))}
                  className="w-full bg-gray-900 border border-gray-700 text-white rounded px-1.5 py-0.5 text-xs font-mono"
                >
                  <option value={1.25}>1.25x</option>
                  <option value={1.5}>1.50x</option>
                  <option value={2.0}>2.00x</option>
                </select>
              </div>
            </div>
          </div>
          <button
            onClick={() => onInjectShock({ shock_type: 'surge', zone: surgeZone, multiplier: surgeMultiplier, duration_min: 30 })}
            className="w-full py-1.5 bg-amber-600 hover:bg-amber-500 text-white font-semibold rounded text-xs transition cursor-pointer"
          >
            Inject Surge (Z{surgeZone} {surgeMultiplier}x)
          </button>
        </div>

        {/* Road Closure */}
        <div className="bg-gray-950/70 p-3 rounded-lg border border-gray-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-1.5 font-bold text-rose-400 mb-1.5">
              <AlertTriangle className="h-4 w-4" />
              <span>Road Closure</span>
            </div>
            <p className="text-[11px] text-gray-400 mb-2">Adds transit delay (5 min) to trips in zone.</p>
            <div className="mb-3">
              <label className="text-[10px] text-gray-500 block">Zone</label>
              <select
                value={closureZone}
                onChange={(e) => setClosureZone(Number(e.target.value))}
                className="w-full bg-gray-900 border border-gray-700 text-white rounded px-1.5 py-0.5 text-xs font-mono"
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((z) => (
                  <option key={z} value={z}>Zone {z}</option>
                ))}
              </select>
            </div>
          </div>
          <button
            onClick={() => onInjectShock({ shock_type: 'closure', zone: closureZone, duration_min: 30 })}
            className="w-full py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded text-xs transition cursor-pointer"
          >
            Inject Closure (Z{closureZone})
          </button>
        </div>

        {/* Order Delay */}
        <div className="bg-gray-950/70 p-3 rounded-lg border border-gray-800 flex flex-col justify-between">
          <div>
            <div className="flex items-center gap-1.5 font-bold text-purple-400 mb-1.5">
              <Clock className="h-4 w-4" />
              <span>Order Prep Delay</span>
            </div>
            <p className="text-[11px] text-gray-400 mb-2">Injects restaurant slip on active orders.</p>
            <div className="flex gap-1 mb-3">
              {[10, 15, 25].map((slip) => (
                <button
                  key={slip}
                  onClick={() => setDelayMinutes(slip)}
                  className={`flex-1 py-1 text-[10px] font-mono font-semibold rounded ${
                    delayMinutes === slip
                      ? 'bg-purple-600 text-white'
                      : 'bg-gray-800 text-gray-400 hover:text-white'
                  } transition cursor-pointer`}
                >
                  +{slip}m
                </button>
              ))}
            </div>
          </div>
          <button
            onClick={() => onInjectShock({ shock_type: 'delay', slip_min: delayMinutes })}
            className="w-full py-1.5 bg-purple-600 hover:bg-purple-500 text-white font-semibold rounded text-xs transition cursor-pointer"
          >
            Inject Slip (+{delayMinutes}m)
          </button>
        </div>
      </div>

      {/* Real-Time Shock Reaction Box */}
      {latestReaction && (
        <div className="bg-gray-950/80 p-3 rounded-lg border border-gray-800 text-xs mt-1">
          <div className="flex items-center justify-between font-semibold text-gray-300 mb-1.5">
            <span className="flex items-center gap-1.5 text-amber-400">
              <AlertTriangle className="h-3.5 w-3.5" />
              <span>Shock Reaction Log ({latestReaction.shock_type.toUpperCase()} at {latestReaction.sim_time})</span>
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-2 text-[11px]">
            <div className="bg-blue-950/20 p-2 rounded border border-blue-900/30">
              <strong className="text-blue-400 block mb-0.5">Baseline Reaction:</strong>
              <p className="text-gray-300 m-0">{latestReaction.baseline_reaction}</p>
            </div>
            <div className="bg-purple-950/20 p-2 rounded border border-purple-900/30">
              <strong className="text-purple-400 block mb-0.5">SmartAgent Reaction:</strong>
              <p className="text-gray-300 m-0">{latestReaction.smart_reaction}</p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
