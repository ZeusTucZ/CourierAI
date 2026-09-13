import React from 'react';
import { Package, ArrowRight, AlertOctagon, CheckCircle2, XCircle } from 'lucide-react';
import type { IncomingOrderInfo } from '../types';

interface IncomingOrderCardProps {
  order: IncomingOrderInfo | null;
  onInspect: (orderId: string) => void;
}

export const IncomingOrderCard: React.FC<IncomingOrderCardProps> = ({ order, onInspect }) => {
  if (!order) {
    return (
      <div className="bg-gray-900/60 border border-dashed border-gray-800 rounded-xl p-6 text-center text-gray-500 text-xs">
        <Package className="h-6 w-6 mx-auto mb-2 opacity-40" />
        <span>Waiting for next incoming order offer...</span>
      </div>
    );
  }

  const bAccept = order.baseline_decision === 'ACCEPT';
  const sAccept = order.smart_decision === 'ACCEPT';

  return (
    <div
      className={`rounded-xl border p-4 transition-all duration-300 ${
        order.is_disagreement
          ? 'bg-amber-950/20 border-amber-500/40 shadow-lg shadow-amber-950/20 ring-1 ring-amber-500/20'
          : 'bg-gray-900 border-gray-800'
      }`}
    >
      {/* Header with order badge and disagreement alert */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800/80 pb-3">
        <div className="flex items-center gap-2">
          <span className="font-mono font-bold text-sm bg-gray-800 px-2.5 py-1 rounded text-white border border-gray-700">
            {order.order_id}
          </span>
          <span className="text-xs text-gray-400 font-mono">
            {order.sim_time} ({order.platform.toUpperCase()})
          </span>
        </div>

        {order.is_disagreement ? (
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse">
            <AlertOctagon className="h-3.5 w-3.5 text-amber-400" />
            <span>DISAGREEMENT</span>
          </span>
        ) : (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-800 text-gray-300 border border-gray-700">
            <span>{order.agreement_summary}</span>
          </span>
        )}
      </div>

      {/* Order Details Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 my-3 text-xs">
        {/* Routing details */}
        <div className="bg-gray-950/60 p-2 rounded border border-gray-800">
          <span className="text-gray-400 block text-[10px] uppercase">Route</span>
          <div className="flex items-center gap-1 font-bold text-white mt-0.5">
            <span>Z{order.zone_pickup}</span>
            <ArrowRight className="h-3 w-3 text-gray-500" />
            <span>Z{order.zone_dropoff}</span>
          </div>
          <span className="text-gray-400 text-[11px] block mt-0.5 font-mono">
            {order.distance_total_km} km total ({order.distance_pickup_km} + {order.distance_delivery_km})
          </span>
        </div>

        {/* Payment */}
        <div className="bg-gray-950/60 p-2 rounded border border-gray-800">
          <span className="text-gray-400 block text-[10px] uppercase">Payout</span>
          <div className="font-bold text-emerald-400 text-sm mt-0.5 font-mono">
            ${(order.base_pay_mxn * order.surge_multiplier + order.est_tip_mxn).toFixed(2)} MXN
          </div>
          <span className="text-gray-400 text-[11px] block mt-0.5">
            Base ${order.base_pay_mxn} + Tip ${order.est_tip_mxn}
          </span>
        </div>

        {/* Surge & Prep */}
        <div className="bg-gray-950/60 p-2 rounded border border-gray-800">
          <span className="text-gray-400 block text-[10px] uppercase">Surge & Prep</span>
          <div className="font-semibold text-white mt-0.5">
            Surge: <strong className="text-amber-400 font-mono">{order.surge_multiplier}x</strong>
          </div>
          <span className="text-gray-400 text-[11px] block mt-0.5 font-mono">
            Prep: {order.restaurant_prep_min} min
          </span>
        </div>

        {/* Cargo */}
        <div className="bg-gray-950/60 p-2 rounded border border-gray-800">
          <span className="text-gray-400 block text-[10px] uppercase">Cargo</span>
          <div className="font-semibold text-white mt-0.5 font-mono">
            {order.weight_kg} kg
          </div>
          <span className="text-gray-400 text-[11px] block mt-0.5">
            Capacity check
          </span>
        </div>
      </div>

      {/* Decision Comparison Footer */}
      <div className="pt-3 border-t border-gray-800/80 grid grid-cols-1 sm:grid-cols-2 gap-3 items-center">
        {/* Baseline Decision */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-gray-950/80 border border-gray-800">
          <span className="text-xs text-gray-400 font-medium">BASELINE:</span>
          <span
            className={`inline-flex items-center gap-1 px-3 py-1 rounded text-xs font-bold font-mono ${
              bAccept
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
            }`}
          >
            {bAccept ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <XCircle className="h-3.5 w-3.5 text-rose-400" />}
            <span>{order.baseline_decision}</span>
          </span>
        </div>

        {/* Smart Decision */}
        <div className="flex items-center justify-between p-2.5 rounded-lg bg-gray-950/80 border border-gray-800">
          <span className="text-xs text-purple-300 font-medium">SMART AGENT:</span>
          <div className="flex items-center gap-2">
            <span
              className={`inline-flex items-center gap-1 px-3 py-1 rounded text-xs font-bold font-mono ${
                sAccept
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                  : 'bg-rose-500/20 text-rose-300 border border-rose-500/40'
              }`}
            >
              {sAccept ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" /> : <XCircle className="h-3.5 w-3.5 text-rose-400" />}
              <span>{order.smart_decision}</span>
            </span>

            <button
              onClick={() => onInspect(order.order_id)}
              className="text-[11px] font-semibold text-purple-400 hover:text-purple-300 underline cursor-pointer"
            >
              Why?
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
