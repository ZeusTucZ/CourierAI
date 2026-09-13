import React, { useState } from 'react';
import type { SimulationState } from '../types';
import { Play, Pause, RotateCcw, ShieldCheck, Zap, TrendingUp, AlertTriangle, CloudRain, Clock, Ban } from 'lucide-react';

interface SimpleHeaderProps {
  state: SimulationState | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onSpeedChange: (speed: 1 | 5 | 10 | 25) => void;
  onInjectShock: (params: any) => void;
  onOpenBenchmark: () => void;
}

export const SimpleHeader: React.FC<SimpleHeaderProps> = ({
  state,
  onStart,
  onPause,
  onResume,
  onReset,
  onSpeedChange,
  onInjectShock,
  onOpenBenchmark,
}) => {
  const [isEventMenuOpen, setIsEventMenuOpen] = useState(false);

  const status = state?.status || 'idle';
  const speed = state?.playback_speed || 5;
  const bNet = state?.baseline.net_earnings_mxn ?? 0;
  const sNet = state?.smart.net_earnings_mxn ?? 0;
  const diff = state?.comparison.net_difference ?? (sNet - bNet);
  const uplift = state?.comparison.uplift_pct ?? 0;

  return (
    <header className="bg-white border-b border-slate-200 sticky top-0 z-40 px-6 py-2.5 shadow-2xs">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        {/* Left: Title, Subtitle, Same Stream Badge */}
        <div className="flex items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-lg font-extrabold tracking-tight text-slate-900 m-0">
                Courier AI Simulator
              </h1>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                Monterrey, MX
              </span>
            </div>
            <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
              <span className="inline-flex items-center gap-1 font-medium text-emerald-700">
                <ShieldCheck className="h-3.5 w-3.5" />
                <span>Same order stream ✓</span>
              </span>
              <span>•</span>
              <span className="font-mono">Seed: {state?.seed || 30004}</span>
              <span>•</span>
              <span className="font-mono font-bold text-slate-800">
                Time: {state?.sim_time || '15:00'}
              </span>
            </div>
          </div>
        </div>

        {/* Center: Live Earnings Comparison (Prominent & Clear) */}
        <div className="flex items-center gap-3 bg-slate-50 border border-slate-200 rounded-xl px-4 py-1.5 shadow-2xs">
          {/* Smart Agent */}
          <div className="text-right">
            <span className="text-[10px] uppercase font-bold text-sky-700 block">Smart</span>
            <strong className="text-base font-bold font-mono text-sky-900">
              ${sNet.toFixed(0)}
            </strong>
          </div>

          <span className="text-slate-300 font-light text-lg">vs</span>

          {/* Baseline */}
          <div>
            <span className="text-[10px] uppercase font-bold text-slate-500 block">Baseline</span>
            <strong className="text-base font-bold font-mono text-slate-700">
              ${bNet.toFixed(0)}
            </strong>
          </div>

          <div className="h-6 w-px bg-slate-200 mx-1" />

          {/* Uplift Spread Badge */}
          <div className="flex items-center gap-1">
            <TrendingUp className="h-3.5 w-3.5 text-emerald-600" />
            <div className="font-mono">
              <span className="text-xs font-extrabold text-emerald-700 block">
                {diff >= 0 ? `+$${diff.toFixed(0)}` : `-$${Math.abs(diff).toFixed(0)}`}
              </span>
              <span className="text-[10px] font-bold text-emerald-600">
                +{uplift.toFixed(1)}%
              </span>
            </div>
          </div>
        </div>

        {/* Right: Simulation Controls & Event Injection */}
        <div className="flex items-center gap-2">
          {/* Speed Selector */}
          <div className="flex items-center bg-slate-100 p-0.5 rounded-lg border border-slate-200">
            {([1, 5, 10, 25] as const).map((s) => (
              <button
                key={s}
                onClick={() => onSpeedChange(s)}
                className={`px-2 py-0.5 text-xs font-mono font-bold rounded transition cursor-pointer ${
                  speed === s
                    ? 'bg-white text-slate-900 shadow-2xs border border-slate-200'
                    : 'text-slate-500 hover:text-slate-800'
                }`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Play / Pause / Resume */}
          {status === 'idle' && (
            <button
              onClick={onStart}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-2xs cursor-pointer"
            >
              <Play className="h-3 w-3 fill-current" />
              <span>START</span>
            </button>
          )}

          {status === 'running' && (
            <button
              onClick={onPause}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-lg bg-amber-600 hover:bg-amber-500 text-white transition shadow-2xs cursor-pointer"
            >
              <Pause className="h-3 w-3 fill-current" />
              <span>PAUSE</span>
            </button>
          )}

          {status === 'paused' && (
            <button
              onClick={onResume}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-bold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-2xs cursor-pointer"
            >
              <Play className="h-3 w-3 fill-current" />
              <span>RESUME</span>
            </button>
          )}

          {/* Reset */}
          <button
            onClick={onReset}
            className="p-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-600 border border-slate-200 transition cursor-pointer"
            title="Reset simulation"
          >
            <RotateCcw className="h-3.5 w-3.5" />
          </button>

          {/* Compact Inject Event Dropdown */}
          <div className="relative">
            <button
              onClick={() => setIsEventMenuOpen(!isEventMenuOpen)}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-semibold rounded-lg bg-amber-50 hover:bg-amber-100 text-amber-900 border border-amber-300 transition cursor-pointer"
              title="Inject exogenous shock"
            >
              <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
              <span>Inject Event</span>
            </button>

            {isEventMenuOpen && (
              <div className="absolute right-0 mt-1.5 w-52 bg-white border border-slate-200 rounded-xl shadow-lg p-1.5 z-50 text-xs flex flex-col gap-1">
                <div className="px-2 py-1 text-[10px] font-bold text-slate-400 uppercase tracking-wider">
                  Select Shock to Inject
                </div>

                <button
                  onClick={() => {
                    onInjectShock({ shock_type: 'rain', duration_min: 30 });
                    setIsEventMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 text-slate-800 transition cursor-pointer"
                >
                  <CloudRain className="h-3.5 w-3.5 text-sky-600" />
                  <span>Rain (30 min)</span>
                </button>

                <button
                  onClick={() => {
                    onInjectShock({ shock_type: 'surge', zone: 7, multiplier: 1.5, duration_min: 30 });
                    setIsEventMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 text-slate-800 transition cursor-pointer"
                >
                  <Zap className="h-3.5 w-3.5 text-amber-600" />
                  <span>Surge (Zone 7, 1.5x)</span>
                </button>

                <button
                  onClick={() => {
                    onInjectShock({ shock_type: 'closure', zone: 1, road: 'Av. Constitución', duration_min: 30 });
                    setIsEventMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 text-slate-800 transition cursor-pointer"
                >
                  <Ban className="h-3.5 w-3.5 text-rose-600" />
                  <span>Road Closure (Av. Constitución)</span>
                </button>

                <button
                  onClick={() => {
                    onInjectShock({ shock_type: 'delay', slip_min: 15 });
                    setIsEventMenuOpen(false);
                  }}
                  className="flex items-center gap-2 w-full text-left px-2 py-1.5 rounded hover:bg-slate-100 text-slate-800 transition cursor-pointer"
                >
                  <Clock className="h-3.5 w-3.5 text-purple-600" />
                  <span>Restaurant Delay (+15 min)</span>
                </button>
              </div>
            )}
          </div>

          {/* Validated Benchmark Button */}
          <button
            onClick={onOpenBenchmark}
            className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 border border-slate-200 transition cursor-pointer"
            title="View 20 held-out shifts validated results"
          >
            Benchmark
          </button>
        </div>
      </div>
    </header>
  );
};
