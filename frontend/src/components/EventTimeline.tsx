import React from 'react';
import { Clock, AlertTriangle, Zap, Shield, Search } from 'lucide-react';
import type { TimelineEventItem } from '../types';

interface EventTimelineProps {
  events: TimelineEventItem[];
  onSelectOrder: (orderId: string) => void;
}

export const EventTimeline: React.FC<EventTimelineProps> = ({ events, onSelectOrder }) => {
  const reversed = [...events].reverse();

  return (
    <div className="bg-gray-900/90 border border-gray-800 rounded-xl p-4 flex flex-col gap-3 h-full">
      <div className="flex items-center justify-between border-b border-gray-800 pb-2">
        <h3 className="text-xs font-bold uppercase tracking-wider text-gray-200 flex items-center gap-1.5 m-0">
          <Clock className="h-4 w-4 text-purple-400" />
          <span>Event Timeline & Decisions ({events.length})</span>
        </h3>
        <span className="text-[10px] text-gray-500 font-mono">Real-time log</span>
      </div>

      <div className="overflow-y-auto max-h-[380px] space-y-2 pr-1">
        {reversed.length > 0 ? (
          reversed.map((e) => {
            const isDisagreement = e.is_disagreement;

            let borderClass = 'border-gray-800/80 bg-gray-950/60';
            let icon = <Clock className="h-3.5 w-3.5 text-gray-400" />;

            if (e.type === 'shock' || e.type === 'shock_injected') {
              borderClass = 'border-amber-500/30 bg-amber-950/20';
              icon = <Zap className="h-3.5 w-3.5 text-amber-400" />;
            } else if (e.type === 'safety_demo') {
              borderClass = 'border-emerald-500/30 bg-emerald-950/20';
              icon = <Shield className="h-3.5 w-3.5 text-emerald-400" />;
            } else if (isDisagreement) {
              borderClass = 'border-amber-500/40 bg-amber-950/30';
              icon = <AlertTriangle className="h-3.5 w-3.5 text-amber-400" />;
            }

            return (
              <div
                key={e.id}
                className={`p-2.5 rounded-lg border text-xs transition flex items-start justify-between gap-3 ${borderClass}`}
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 shrink-0">{icon}</span>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-gray-400 text-[11px] font-semibold">{e.sim_time}</span>
                      <strong className="text-gray-200">{e.title}</strong>
                      {isDisagreement && (
                        <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          DISAGREE
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-2 m-0">{e.description}</p>
                  </div>
                </div>

                {e.order_id && (
                  <button
                    onClick={() => onSelectOrder(e.order_id!)}
                    className="shrink-0 flex items-center gap-1 text-[11px] text-purple-400 hover:text-purple-300 font-semibold px-2 py-1 rounded bg-gray-900 border border-gray-700 hover:border-purple-500/50 transition cursor-pointer"
                    title="Open Smart decision inspector for this order"
                  >
                    <Search className="h-3 w-3" />
                    <span>Inspect</span>
                  </button>
                )}
              </div>
            );
          })
        ) : (
          <p className="text-xs text-gray-500 italic py-4 text-center m-0">
            No events recorded yet. Start the shift to view chronological stream.
          </p>
        )}
      </div>
    </div>
  );
};
