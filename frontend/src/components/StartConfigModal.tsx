import React, { useState } from 'react';
import { X, Settings, Sparkles, Check } from 'lucide-react';

interface StartConfigModalProps {
  isOpen: boolean;
  onClose: () => void;
  onApply: (config: {
    seed: number;
    shift_hours: number;
    vehicle: 'moto' | 'car' | 'bike';
    start_location_zone: number;
    playback_speed: number;
  }) => void;
}

export const StartConfigModal: React.FC<StartConfigModalProps> = ({ isOpen, onClose, onApply }) => {
  const [seed, setSeed] = useState<number>(30004);
  const [shiftHours, setShiftHours] = useState<number>(8);
  const [vehicle, setVehicle] = useState<'moto' | 'car' | 'bike'>('moto');
  const [startZone, setStartZone] = useState<number>(7);
  const [speed, setSpeed] = useState<number>(5);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    onApply({
      seed,
      shift_hours: shiftHours,
      vehicle,
      start_location_zone: startZone,
      playback_speed: speed,
    });
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-gray-900 border border-gray-800 rounded-2xl w-full max-w-md p-6 shadow-2xl flex flex-col gap-4">
        <div className="flex items-center justify-between border-b border-gray-800 pb-3">
          <div className="flex items-center gap-2">
            <Settings className="h-5 w-5 text-purple-400" />
            <h2 className="text-base font-bold text-white m-0">Configure Shift Demo</h2>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 hover:text-white transition cursor-pointer"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-3.5 text-xs">
          {/* Seed input */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="text-gray-300 font-semibold">Demo Seed</label>
              <button
                type="button"
                onClick={() => setSeed(30004)}
                className="text-[10px] text-purple-400 hover:text-purple-300 underline cursor-pointer flex items-center gap-1"
              >
                <Sparkles className="h-3 w-3" />
                <span>Reset to Recommended (30004)</span>
              </button>
            </div>
            <input
              type="number"
              value={seed}
              onChange={(e) => setSeed(Number(e.target.value))}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white font-mono text-xs focus:border-purple-500 outline-none"
              placeholder="e.g. 30004"
            />
            <p className="text-[10px] text-gray-500 mt-1">
              Note: Seeds 1–10 (tuning) and 10001–10020 (held-out evaluation) are reserved. Use new demo seeds (e.g. 30004).
            </p>
          </div>

          {/* Shift Hours */}
          <div>
            <label className="text-gray-300 font-semibold block mb-1">Shift Duration (Hours)</label>
            <select
              value={shiftHours}
              onChange={(e) => setShiftHours(Number(e.target.value))}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-xs font-mono focus:border-purple-500 outline-none"
            >
              <option value={4}>4 Hours (Part-time)</option>
              <option value={8}>8 Hours (Standard Shift: 15:00 - 23:00)</option>
              <option value={10}>10 Hours (Full Day)</option>
            </select>
          </div>

          {/* Vehicle */}
          <div>
            <label className="text-gray-300 font-semibold block mb-1">Vehicle Type</label>
            <div className="grid grid-cols-3 gap-2">
              {(['moto', 'car', 'bike'] as const).map((v) => (
                <button
                  type="button"
                  key={v}
                  onClick={() => setVehicle(v)}
                  className={`py-2 rounded-lg font-semibold uppercase text-xs border ${
                    vehicle === v
                      ? 'bg-purple-600 text-white border-purple-500 shadow'
                      : 'bg-gray-950 text-gray-400 border-gray-800 hover:text-white'
                  } transition cursor-pointer`}
                >
                  {v}
                </button>
              ))}
            </div>
          </div>

          {/* Start Zone */}
          <div>
            <label className="text-gray-300 font-semibold block mb-1">Starting Zone</label>
            <select
              value={startZone}
              onChange={(e) => setStartZone(Number(e.target.value))}
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-white text-xs font-mono focus:border-purple-500 outline-none"
            >
              {Array.from({ length: 12 }, (_, i) => i + 1).map((z) => (
                <option key={z} value={z}>Zone {z} {z === 7 ? '(Default Center)' : ''}</option>
              ))}
            </select>
          </div>

          {/* Playback speed */}
          <div>
            <label className="text-gray-300 font-semibold block mb-1">Initial Playback Speed</label>
            <div className="grid grid-cols-4 gap-2">
              {[1, 5, 10, 25].map((s) => (
                <button
                  type="button"
                  key={s}
                  onClick={() => setSpeed(s)}
                  className={`py-1.5 rounded-lg font-mono font-bold text-xs border ${
                    speed === s
                      ? 'bg-purple-600 text-white border-purple-500'
                      : 'bg-gray-950 text-gray-400 border-gray-800 hover:text-white'
                  } transition cursor-pointer`}
                >
                  {s}x
                </button>
              ))}
            </div>
          </div>

          <div className="pt-3 border-t border-gray-800 flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded-lg text-xs font-medium transition cursor-pointer"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-bold transition flex items-center gap-1.5 cursor-pointer"
            >
              <Check className="h-3.5 w-3.5" />
              <span>Apply & Reset</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
