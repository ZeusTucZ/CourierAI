import React from 'react';
import { Play, Pause, RotateCcw, Zap, AlertTriangle, ShieldCheck, Settings, Award } from 'lucide-react';
import type { SimulationState } from '../types';

interface HeaderProps {
  state: SimulationState | null;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onReset: () => void;
  onSpeedChange: (speed: 1 | 5 | 10 | 25) => void;
  onOpenSettings: () => void;
  onOpenHistorical: () => void;
  activeView?: 'map' | 'detailed';
  onToggleView?: (view: 'map' | 'detailed') => void;
}

export const Header: React.FC<HeaderProps> = ({
  state,
  onStart,
  onPause,
  onResume,
  onReset,
  onSpeedChange,
  onOpenSettings,
  onOpenHistorical,
  activeView = 'map',
  onToggleView,
}) => {
  const status = state?.status || 'idle';
  const speed = state?.playback_speed || 5;

  return (
    <header className="border-b border-gray-800 bg-gray-900/90 backdrop-blur sticky top-0 z-40 px-6 py-3">
      <div className="flex flex-wrap items-center justify-between gap-4">
        {/* Title & Status */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Zap className="h-6 w-6 text-purple-400" />
            <h1 className="text-xl font-bold tracking-tight text-white m-0 p-0">
              COURIER AI <span className="text-gray-500 font-normal">| SAME SHIFT COMPARISON</span>
            </h1>
          </div>
          
          <div className="flex items-center gap-2 ml-2">
            <span
              className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                status === 'running'
                  ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 animate-pulse'
                  : status === 'paused'
                  ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                  : status === 'completed'
                  ? 'bg-blue-500/20 text-blue-400 border border-blue-500/30'
                  : 'bg-gray-800 text-gray-400 border border-gray-700'
              }`}
            >
              {status.toUpperCase()}
            </span>

            {/* Same event stream tag */}
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-950/60 text-emerald-300 text-xs border border-emerald-700/50">
              <ShieldCheck className="h-3.5 w-3.5 text-emerald-400" />
              <span>Same Stream ✓</span>
              <span className="text-emerald-400/70 font-mono text-[11px] ml-1">
                {state?.stream_hash || 'verified'}
              </span>
            </span>
          </div>
        </div>

        {/* Global Shift Info Badges */}
        <div className="flex items-center gap-2 text-xs font-medium text-gray-300">
          <div className="bg-gray-800/80 px-2.5 py-1 rounded border border-gray-700">
            <span className="text-gray-400">Seed:</span> <strong className="text-white font-mono">{state?.seed || 30004}</strong>
          </div>
          <div className="bg-gray-800/80 px-2.5 py-1 rounded border border-gray-700">
            <span className="text-gray-400">Time:</span> <strong className="text-white font-mono">{state?.sim_time || '15:00'}</strong> <span className="text-gray-500">/ 23:00</span>
          </div>
          <div className="bg-gray-800/80 px-2.5 py-1 rounded border border-gray-700">
            <span className="text-gray-400">Vehicle:</span> <strong className="text-purple-300 capitalize">{state?.vehicle || 'moto'}</strong>
          </div>

          {/* Shock Badge if active */}
          {state?.current_shock && (
            <div className="bg-amber-500/20 text-amber-300 border border-amber-500/40 px-2.5 py-1 rounded flex items-center gap-1.5 animate-pulse font-semibold">
              <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />
              <span>{state.current_shock.message}</span>
            </div>
          )}
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {/* View Selector (Map vs Detailed) */}
          {onToggleView && (
            <div className="flex items-center bg-gray-950 p-0.5 rounded-lg border border-gray-800 text-xs font-semibold">
              <button
                onClick={() => onToggleView('map')}
                className={`px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 ${
                  activeView === 'map' ? 'bg-emerald-600 text-white shadow' : 'text-gray-400 hover:text-white'
                }`}
                title="Vista principal: Mapa real interactivo de Monterrey"
              >
                <span>🗺️ Mapa Real</span>
              </button>
              <button
                onClick={() => onToggleView('detailed')}
                className={`px-2.5 py-1 rounded transition cursor-pointer flex items-center gap-1.5 ${
                  activeView === 'detailed' ? 'bg-purple-600 text-white shadow' : 'text-gray-400 hover:text-white'
                }`}
                title="Vista detallada: Comparativa 50/50 de métricas"
              >
                <span>📊 50/50 Detalle</span>
              </button>
            </div>
          )}

          {/* Historical validation button */}
          <button
            onClick={onOpenHistorical}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-gray-800 hover:bg-gray-700 text-purple-300 border border-purple-500/30 transition shadow-sm cursor-pointer"
            title="View offline 20-shift held-out benchmark results"
          >
            <Award className="h-3.5 w-3.5 text-purple-400" />
            <span className="hidden sm:inline">Held-Out Stats (20 Shifts)</span>
            <span className="sm:hidden">Benchmark</span>
          </button>

          {/* Config / Seed Settings */}
          <button
            onClick={onOpenSettings}
            disabled={status === 'running'}
            className="p-1.5 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-40 text-gray-300 border border-gray-700 transition cursor-pointer"
            title="Configure simulation parameters"
          >
            <Settings className="h-4 w-4" />
          </button>

          {/* Playback Speeds */}
          <div className="flex items-center bg-gray-950 p-0.5 rounded-lg border border-gray-800">
            {([1, 5, 10, 25] as const).map((s) => (
              <button
                key={s}
                onClick={() => onSpeedChange(s)}
                className={`px-2 py-1 text-xs font-mono font-semibold rounded ${
                  speed === s
                    ? 'bg-purple-600 text-white shadow'
                    : 'text-gray-400 hover:text-white'
                } transition cursor-pointer`}
              >
                {s}x
              </button>
            ))}
          </div>

          {/* Main Simulation Control Buttons */}
          {status === 'idle' && (
            <button
              onClick={onStart}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm cursor-pointer"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>START SHIFT</span>
            </button>
          )}

          {status === 'running' && (
            <button
              onClick={onPause}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-amber-600 hover:bg-amber-500 text-white transition shadow-sm cursor-pointer"
            >
              <Pause className="h-3.5 w-3.5 fill-current" />
              <span>PAUSE</span>
            </button>
          )}

          {status === 'paused' && (
            <button
              onClick={onResume}
              className="flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition shadow-sm cursor-pointer"
            >
              <Play className="h-3.5 w-3.5 fill-current" />
              <span>RESUME</span>
            </button>
          )}

          <button
            onClick={onReset}
            className="flex items-center gap-1 px-2.5 py-1.5 text-xs font-medium rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-300 border border-gray-700 transition cursor-pointer"
            title="Reset simulation to start"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>RESET</span>
          </button>
        </div>
      </div>
    </header>
  );
};
