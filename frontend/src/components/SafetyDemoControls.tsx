import React from 'react';
import { ShieldAlert, Scale, Clock, Moon } from 'lucide-react';

interface SafetyDemoControlsProps {
  onTriggerScenario: (scenarioType: 'vehicle_capacity' | 'shift_end_infeasible' | 'flagged_zone_night') => void;
}

export const SafetyDemoControls: React.FC<SafetyDemoControlsProps> = ({ onTriggerScenario }) => {
  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-gray-800 pb-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-200 flex items-center gap-1.5 m-0">
          <ShieldAlert className="h-4 w-4 text-emerald-400" />
          <span>Demo Scenarios: Verified Hard Constraints</span>
        </h3>
        <span className="text-[10px] text-gray-500 font-mono">Real /decide constraint evaluation</span>
      </div>

      <p className="text-[11px] text-gray-400 m-0">
        Click any scenario to inject a real offer that directly tests the hard constraints pipeline. Both agents evaluate the offer and reject it with <code className="text-amber-400 font-mono">SKIP</code> and the official constraint name.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1">
        {/* Scenario 1: Vehicle Capacity */}
        <button
          onClick={() => onTriggerScenario('vehicle_capacity')}
          className="flex items-start gap-2.5 p-3 rounded-lg bg-gray-950/80 hover:bg-gray-950 border border-gray-800 hover:border-emerald-500/40 text-left transition cursor-pointer group"
        >
          <Scale className="h-4 w-4 text-emerald-400 mt-0.5 shrink-0 group-hover:scale-110 transition-transform" />
          <div>
            <div className="text-xs font-bold text-white group-hover:text-emerald-300">
              Vehicle Capacity Exceeded
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5 m-0">
              Injects heavy package (50 kg &gt; 15 kg limit). Demonstrates physical capacity check.
            </p>
            <span className="inline-block mt-1.5 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-1.5 py-0.5 rounded border border-emerald-800/40">
              → SKIP: vehicle_capacity
            </span>
          </div>
        </button>

        {/* Scenario 2: Shift End Infeasible */}
        <button
          onClick={() => onTriggerScenario('shift_end_infeasible')}
          className="flex items-start gap-2.5 p-3 rounded-lg bg-gray-950/80 hover:bg-gray-950 border border-gray-800 hover:border-amber-500/40 text-left transition cursor-pointer group"
        >
          <Clock className="h-4 w-4 text-amber-400 mt-0.5 shrink-0 group-hover:scale-110 transition-transform" />
          <div>
            <div className="text-xs font-bold text-white group-hover:text-amber-300">
              Shift End Infeasible
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5 m-0">
              Injects order near shift end whose trip exceeds 23:00. Demonstrates shift duration bounds.
            </p>
            <span className="inline-block mt-1.5 text-[10px] font-mono text-amber-400 bg-amber-950/60 px-1.5 py-0.5 rounded border border-amber-800/40">
              → SKIP: shift_end_infeasible
            </span>
          </div>
        </button>

        {/* Scenario 3: Flagged Zone Night */}
        <button
          onClick={() => onTriggerScenario('flagged_zone_night')}
          className="flex items-start gap-2.5 p-3 rounded-lg bg-gray-950/80 hover:bg-gray-950 border border-gray-800 hover:border-purple-500/40 text-left transition cursor-pointer group"
        >
          <Moon className="h-4 w-4 text-purple-400 mt-0.5 shrink-0 group-hover:scale-110 transition-transform" />
          <div>
            <div className="text-xs font-bold text-white group-hover:text-purple-300">
              Flagged Zone Night
            </div>
            <p className="text-[11px] text-gray-400 mt-0.5 m-0">
              Injects night delivery to high-risk Zone 11 (after 22:00). Demonstrates curfew restriction.
            </p>
            <span className="inline-block mt-1.5 text-[10px] font-mono text-purple-400 bg-purple-950/60 px-1.5 py-0.5 rounded border border-purple-800/40">
              → SKIP: flagged_zone_night
            </span>
          </div>
        </button>
      </div>
    </div>
  );
};
