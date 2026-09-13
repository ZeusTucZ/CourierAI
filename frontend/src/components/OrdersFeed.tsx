import React, { useState, useEffect, useRef } from 'react';
import type { TimelineEventItem, DecisionInspectorData } from '../types';
import { getZoneName } from '../monterreyGeo';
import { AlertCircle, AlertTriangle, ChevronDown, ChevronUp, Clock, ArrowRight } from 'lucide-react';

interface OrdersFeedProps {
  events: TimelineEventItem[];
  onFetchDecisionInspector?: (orderId: string) => Promise<DecisionInspectorData | null>;
}

export const OrdersFeed: React.FC<OrdersFeedProps> = ({
  events,
  onFetchDecisionInspector,
}) => {
  const [expandedOrderId, setExpandedOrderId] = useState<string | null>(null);
  const [inspectorCache, setInspectorCache] = useState<Record<string, DecisionInspectorData>>({});
  const [loadingOrderId, setLoadingOrderId] = useState<string | null>(null);
  const [isUserScrolled, setIsUserScrolled] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);

  // Filter out redundant non-order non-shock events or keep all chronological events
  const feedEvents = [...events].reverse();

  // Auto-scroll to latest event if user is not actively inspecting an older card
  useEffect(() => {
    if (!isUserScrolled && !expandedOrderId && containerRef.current) {
      containerRef.current.scrollTop = 0;
    }
  }, [events.length, isUserScrolled, expandedOrderId]);

  const handleToggleWhy = async (orderId: string) => {
    if (expandedOrderId === orderId) {
      setExpandedOrderId(null);
      return;
    }

    setExpandedOrderId(orderId);

    if (!inspectorCache[orderId] && onFetchDecisionInspector) {
      setLoadingOrderId(orderId);
      try {
        const data = await onFetchDecisionInspector(orderId);
        if (data) {
          setInspectorCache((prev) => ({ ...prev, [orderId]: data }));
        }
      } catch (err) {
        console.error('Error fetching decision detail:', err);
      } finally {
        setLoadingOrderId(null);
      }
    }
  };

  const handleScroll = () => {
    if (!containerRef.current) return;
    // If scrolled down more than 40px, assume user is manually inspecting
    setIsUserScrolled(containerRef.current.scrollTop > 40);
  };

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-200 bg-slate-50 flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-900 m-0 tracking-tight flex items-center gap-2">
            <span>Orders</span>
            <span className="text-xs font-mono font-medium px-2 py-0.5 rounded bg-slate-200 text-slate-700">
              {feedEvents.filter((e) => e.type === 'order_decision').length} decisions
            </span>
          </h2>
        </div>
        {isUserScrolled && (
          <button
            onClick={() => {
              setIsUserScrolled(false);
              setExpandedOrderId(null);
              containerRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
            }}
            className="text-[11px] text-sky-600 hover:text-sky-800 font-semibold cursor-pointer"
          >
            Jump to latest ➔
          </button>
        )}
      </div>

      {/* Scrollable Feed */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 p-3 overflow-y-auto space-y-3 max-h-[820px]"
      >
        {feedEvents.length === 0 && (
          <div className="p-8 text-center text-slate-400 text-xs">
            Waiting for first order to arrive...
          </div>
        )}

        {feedEvents.map((item) => {
          // A. Shock Event Card
          if (item.type === 'shock' || item.type === 'shock_injected') {
            return (
              <div
                key={item.id}
                className="bg-amber-50 border border-amber-300 rounded-lg p-3 text-xs shadow-2xs"
              >
                <div className="flex items-center justify-between font-bold text-amber-900 mb-1">
                  <span className="flex items-center gap-1.5 uppercase text-[11px] tracking-wider">
                    <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                    <span>{item.title}</span>
                  </span>
                  <span className="font-mono text-[10px] text-amber-800">{item.sim_time}</span>
                </div>
                <p className="text-amber-800 m-0 text-xs leading-relaxed">
                  {item.description}
                </p>
              </div>
            );
          }

          // B. Shift End Event Card
          if (item.type === 'shift_end') {
            return (
              <div
                key={item.id}
                className="bg-emerald-50 border border-emerald-300 rounded-lg p-3 text-xs shadow-2xs text-center"
              >
                <strong className="text-emerald-900 block text-xs uppercase tracking-wider mb-0.5">
                  Shift Completed
                </strong>
                <span className="text-emerald-700 text-xs">{item.description}</span>
              </div>
            );
          }

          // C. Order Decision Card
          const isExpanded = expandedOrderId === item.order_id;
          const cached = item.order_id ? inspectorCache[item.order_id] : null;
          const isDisagreement = item.is_disagreement;

          // Parse basic info from description if available
          const orderId = item.order_id || `ORD-${item.id}`;

          return (
            <div
              key={item.id}
              className={`rounded-lg border text-xs transition-all shadow-2xs ${
                isDisagreement
                  ? 'bg-amber-50/50 border-amber-300 ring-1 ring-amber-200'
                  : 'bg-white border-slate-200 hover:border-slate-300'
              }`}
            >
              {/* Top Banner for Disagreements */}
              {isDisagreement && (
                <div className="bg-amber-100/80 px-3 py-1 border-b border-amber-200 flex items-center justify-between text-[11px] font-bold text-amber-900">
                  <span className="flex items-center gap-1">
                    <AlertCircle className="h-3.5 w-3.5 text-amber-700" />
                    <span>Different decision</span>
                  </span>
                  <span className="font-normal text-[10px] text-amber-700">Smart diverted from baseline</span>
                </div>
              )}

              <div className="p-3">
                {/* Order Top Bar: ID and Time */}
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <strong className="text-slate-900 font-mono text-sm">{orderId}</strong>
                  </div>
                  <span className="text-slate-500 font-mono text-xs flex items-center gap-1">
                    <Clock className="h-3 w-3 text-slate-400" />
                    <span>{item.sim_time}</span>
                  </span>
                </div>

                {/* Offer Route & Estimate (from cache if loaded, or description) */}
                {cached && (
                  <div className="mb-2.5 pb-2 border-b border-slate-100">
                    <div className="flex items-center gap-1.5 font-semibold text-slate-800 text-xs mb-1">
                      <span>{getZoneName(cached.offer_details.zone_pickup)}</span>
                      <ArrowRight className="h-3 w-3 text-slate-400" />
                      <span>{getZoneName(cached.offer_details.zone_dropoff)}</span>
                    </div>
                    <div className="flex items-center justify-between text-[11px] text-slate-500 font-mono">
                      <span>{cached.offer_details.distance_total_km.toFixed(1)} km</span>
                      <strong className="text-emerald-700">
                        ${(cached.offer_details.base_pay_mxn * cached.offer_details.surge_multiplier + cached.offer_details.est_tip_mxn).toFixed(2)} MXN
                      </strong>
                    </div>
                  </div>
                )}

                {/* Side-by-Side Decision Badges */}
                <div className="grid grid-cols-2 gap-2 text-center mb-2.5">
                  {/* Baseline Decision */}
                  <div className="bg-slate-50 p-2 rounded-lg border border-slate-200">
                    <span className="text-[10px] uppercase font-bold text-slate-400 block mb-0.5">Baseline</span>
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold font-mono ${
                      cached?.baseline.decision === 'ACCEPT'
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                        : 'bg-rose-100 text-rose-800 border border-rose-300'
                    }`}>
                      {cached?.baseline.decision || (item.description.includes('Baseline: ACCEPT') ? 'ACCEPT' : 'SKIP')}
                    </span>
                  </div>

                  {/* Smart Decision */}
                  <div className="bg-sky-50/50 p-2 rounded-lg border border-sky-200">
                    <span className="text-[10px] uppercase font-bold text-sky-700 block mb-0.5">Smart Agent</span>
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold font-mono ${
                      cached?.smart.decision === 'ACCEPT'
                        ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                        : 'bg-rose-100 text-rose-800 border border-rose-300'
                    }`}>
                      {cached?.smart.decision || (item.description.includes('Smart: ACCEPT') ? 'ACCEPT' : 'SKIP')}
                    </span>
                  </div>
                </div>

                {/* "Why?" Expand Toggle Button */}
                {item.order_id && (
                  <button
                    onClick={() => handleToggleWhy(item.order_id!)}
                    className="w-full text-left py-1.5 px-2.5 rounded bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-700 font-semibold flex items-center justify-between transition cursor-pointer text-xs"
                  >
                    <span className="flex items-center gap-1 text-sky-700">
                      <span>Why?</span>
                      <span className="text-slate-500 font-normal text-[11px]">(Click to inspect reason)</span>
                    </span>
                    {isExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                  </button>
                )}

                {/* Expanded Decision Explanation Detail */}
                {isExpanded && (
                  <div className="mt-2.5 p-3 rounded-lg bg-sky-50/80 border border-sky-200 text-xs space-y-2 animate-in fade-in duration-150">
                    {loadingOrderId === item.order_id ? (
                      <span className="text-slate-500 italic">Loading decision data...</span>
                    ) : cached ? (
                      <>
                        <div>
                          <span className="text-[10px] uppercase font-bold text-sky-900 block tracking-wider">
                            SMART DECISION
                          </span>
                          <span className={`font-mono font-bold text-sm ${
                            cached.smart.decision === 'ACCEPT' ? 'text-emerald-700' : 'text-rose-700'
                          }`}>
                            {cached.smart.decision}
                          </span>
                          {cached.smart.binding_constraint && (
                            <span className="ml-2 text-[10px] bg-rose-100 text-rose-800 border border-rose-300 px-1.5 py-0.5 rounded font-mono">
                              SAFETY: {cached.smart.binding_constraint}
                            </span>
                          )}
                        </div>

                        <div>
                          <span className="text-[10px] uppercase font-bold text-slate-500 block">Reason</span>
                          <p className="text-slate-800 m-0 leading-relaxed font-medium">
                            {cached.smart.reason || 'Decision recorded in simulator.'}
                          </p>
                        </div>

                        {/* Economic Breakdown from real decision log */}
                        <div className="grid grid-cols-2 gap-2 pt-1 border-t border-sky-200/60 font-mono text-[11px]">
                          <div>
                            <span className="text-slate-500 block text-[10px]">Net pay:</span>
                            <strong className="text-slate-900">
                              ${(cached.smart.economics.net_pay_mxn ?? 0).toFixed(2)}
                            </strong>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[10px]">Estimated time:</span>
                            <strong className="text-slate-900">
                              {(cached.offer_details.restaurant_prep_min + cached.offer_details.distance_total_km * 2).toFixed(0)} min
                            </strong>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[10px]">Adjusted rate:</span>
                            <strong className="text-sky-800">
                              ${(cached.smart.economics.adjusted_rate_mxn_hr ?? 0).toFixed(2)}/hr
                            </strong>
                          </div>
                          <div>
                            <span className="text-slate-500 block text-[10px]">Reservation wage:</span>
                            <strong className="text-slate-900">
                              ${(cached.smart.economics.reservation_wage_mxn_hr ?? 125.0).toFixed(2)}/hr
                            </strong>
                          </div>
                        </div>
                      </>
                    ) : (
                      <p className="text-slate-700 m-0 leading-relaxed">
                        {item.description}
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
