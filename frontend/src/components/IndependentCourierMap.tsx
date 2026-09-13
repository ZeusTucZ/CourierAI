import React, { useEffect, useRef } from 'react';
import L from 'leaflet';
import type { AgentState, IncomingOrderInfo, ShockInfo } from '../types';
import { MONTERREY_METRO_CENTER, DEFAULT_MAP_ZOOM, getZoneCenter, getZoneName } from '../monterreyGeo';
import { MapPin, AlertTriangle, HelpCircle } from 'lucide-react';

interface IndependentCourierMapProps {
  agentType: 'baseline' | 'smart';
  title: string;
  subtitle: string;
  agent: AgentState | null;
  incomingOrder: IncomingOrderInfo | null;
  currentShock: ShockInfo | null;
  simTime: string;
  onInspectOrder?: (orderId: string) => void;
}

export const IndependentCourierMap: React.FC<IndependentCourierMapProps> = ({
  agentType,
  title,
  subtitle,
  agent,
  incomingOrder,
  currentShock,
  simTime,
  onInspectOrder,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);

  // Layer refs
  const courierMarkerRef = useRef<L.Marker | null>(null);
  const pickupMarkerRef = useRef<L.Marker | null>(null);
  const dropoffMarkerRef = useRef<L.Marker | null>(null);
  const routePolylineRef = useRef<L.Polyline | null>(null);
  const closureLayerRef = useRef<L.LayerGroup | null>(null);

  const isSmart = agentType === 'smart';
  const currentZone = agent?.current_zone ?? 7;

  // Initialize Independent Leaflet Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: MONTERREY_METRO_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
      zoomControl: true,
      attributionControl: true,
    });

    // Clean OpenStreetMap Tile Layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 18,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    }).addTo(map);

    closureLayerRef.current = L.layerGroup().addTo(map);
    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // Update Courier Marker
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    const coords = getZoneCenter(currentZone);

    const markerColor = isSmart ? '#0284c7' : '#475569';
    const pulseClass = isSmart ? 'pulse-smart' : 'pulse-baseline';

    const courierHtml = `
      <div class="${pulseClass}" style="
        width: 32px;
        height: 32px;
        border-radius: 50%;
        background: ${markerColor};
        border: 2px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3);
        font-size: 15px;
        cursor: pointer;
        position: relative;
      ">
        <span>${isSmart ? '⚡' : '🛵'}</span>
        <div style="
          position: absolute;
          bottom: -18px;
          background: #ffffff;
          color: #1e293b;
          font-size: 9px;
          font-weight: 700;
          padding: 1px 5px;
          border-radius: 4px;
          border: 1px solid #cbd5e1;
          white-space: nowrap;
          box-shadow: 0 1px 3px rgba(0,0,0,0.15);
        ">
          ${isSmart ? 'Smart' : 'Baseline'}
        </div>
      </div>
    `;

    const courierIcon = L.divIcon({
      className: `courier-marker-${agentType}`,
      html: courierHtml,
      iconSize: [32, 32],
      iconAnchor: [16, 16],
    });

    if (!courierMarkerRef.current) {
      courierMarkerRef.current = L.marker(coords, { icon: courierIcon, zIndexOffset: 900 }).addTo(map);
    } else {
      courierMarkerRef.current.setLatLng(coords);
      courierMarkerRef.current.setIcon(courierIcon);
    }

    courierMarkerRef.current.bindPopup(`
      <div style="font-size: 11px; font-family: inherit; line-height: 1.4;">
        <strong style="color: ${markerColor}; font-size: 12px; display: block; margin-bottom: 2px;">
          ${isSmart ? 'SmartAgent' : 'FirstNearbyOrderBaseline'}
        </strong>
        <strong>Zona actual:</strong> ${currentZone} (${getZoneName(currentZone)})<br/>
        <strong>Estado:</strong> ${agent?.status || 'idle'}<br/>
        <strong>Ganancia neta:</strong> $${(agent?.net_earnings_mxn ?? 0).toFixed(2)} MXN<br/>
        <strong>Distancia:</strong> ${(agent?.distance_traveled_km ?? 0).toFixed(1)} km
      </div>
    `);
  }, [currentZone, agentType, isSmart, agent?.net_earnings_mxn, agent?.status, agent?.distance_traveled_km]);

  // Update Route and Order Pins
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // Check if there is an active order or an evaluated incoming order
    const hasOrder = !!incomingOrder;

    if (!hasOrder) {
      if (pickupMarkerRef.current) {
        map.removeLayer(pickupMarkerRef.current);
        pickupMarkerRef.current = null;
      }
      if (dropoffMarkerRef.current) {
        map.removeLayer(dropoffMarkerRef.current);
        dropoffMarkerRef.current = null;
      }
      if (routePolylineRef.current) {
        map.removeLayer(routePolylineRef.current);
        routePolylineRef.current = null;
      }
      return;
    }

    const pCoords = getZoneCenter(incomingOrder.zone_pickup);
    const dCoords = getZoneCenter(incomingOrder.zone_dropoff);
    const cCoords = getZoneCenter(currentZone);

    // Pickup Pin (Green)
    const pickupHtml = `
      <div style="
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #16a34a;
        border: 2px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 13px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
        cursor: pointer;
      ">
        🍴
      </div>
    `;

    const pickupIcon = L.divIcon({
      className: 'order-pickup-pin',
      html: pickupHtml,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });

    if (!pickupMarkerRef.current) {
      pickupMarkerRef.current = L.marker(pCoords, { icon: pickupIcon, zIndexOffset: 700 }).addTo(map);
    } else {
      pickupMarkerRef.current.setLatLng(pCoords);
      pickupMarkerRef.current.setIcon(pickupIcon);
    }

    // Dropoff Pin (Red)
    const dropoffHtml = `
      <div style="
        width: 28px;
        height: 28px;
        border-radius: 50%;
        background: #dc2626;
        border: 2px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        font-size: 13px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.25);
        cursor: pointer;
      ">
        📍
      </div>
    `;

    const dropoffIcon = L.divIcon({
      className: 'order-dropoff-pin',
      html: dropoffHtml,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });

    if (!dropoffMarkerRef.current) {
      dropoffMarkerRef.current = L.marker(dCoords, { icon: dropoffIcon, zIndexOffset: 700 }).addTo(map);
    } else {
      dropoffMarkerRef.current.setLatLng(dCoords);
      dropoffMarkerRef.current.setIcon(dropoffIcon);
    }

    // Connect Courier -> Pickup -> Dropoff
    const routePoints = [cCoords, pCoords, dCoords];
    const isClosure = currentShock?.shock_type === 'closure';
    const routeColor = isClosure ? '#ea580c' : (isSmart ? '#0284c7' : '#64748b');

    if (!routePolylineRef.current) {
      routePolylineRef.current = L.polyline(routePoints, {
        color: routeColor,
        weight: isSmart ? 4 : 3,
        opacity: 0.85,
        dashArray: isClosure ? '6, 6' : undefined,
      }).addTo(map);
    } else {
      routePolylineRef.current.setLatLngs(routePoints);
      routePolylineRef.current.setStyle({
        color: routeColor,
        dashArray: isClosure ? '6, 6' : undefined,
      });
    }
  }, [incomingOrder, currentZone, isSmart, currentShock]);

  // Road Closure Overlay
  useEffect(() => {
    const group = closureLayerRef.current;
    if (!group) return;

    group.clearLayers();

    if (currentShock?.shock_type === 'closure') {
      const closureCoords = getZoneCenter(currentZone);
      const closureMarker = L.marker([closureCoords[0] + 0.005, closureCoords[1] - 0.005], {
        icon: L.divIcon({
          className: 'closure-pin',
          html: `
            <div style="
              background: #fef2f2;
              border: 1.5px solid #dc2626;
              color: #b91c1c;
              font-size: 10px;
              font-weight: 800;
              padding: 2px 6px;
              border-radius: 6px;
              display: inline-flex;
              align-items: center;
              gap: 3px;
              box-shadow: 0 2px 6px rgba(0,0,0,0.15);
              white-space: nowrap;
            ">
              <span>🚫 Cierre Vial</span>
              ${isSmart ? '<span style="color:#0284c7;font-size:9px;">(Rerouting)</span>' : ''}
            </div>
          `,
          iconSize: [110, 22],
          iconAnchor: [55, 11],
        }),
      });
      group.addLayer(closureMarker);
    }
  }, [currentShock, currentZone, isSmart]);

  // Current Decision computation
  const decision = isSmart
    ? (incomingOrder?.smart_decision || agent?.last_decision.decision || '—')
    : (incomingOrder?.baseline_decision || agent?.last_decision.decision || '—');

  // Baseline decision description
  let baselineReasonText = '';
  if (!isSmart) {
    if (decision === 'ACCEPT') {
      baselineReasonText = 'Within nearby-distance threshold';
    } else if (decision === 'SKIP') {
      baselineReasonText = agent?.last_decision.binding_constraint
        ? `Hard constraint: ${agent.last_decision.binding_constraint}`
        : 'Too far (>15 km threshold)';
    } else {
      baselineReasonText = 'Waiting for offers';
    }
  }

  // Smart decision explanation
  let smartExplanationText = '';
  if (isSmart) {
    if (incomingOrder?.smart_reason) {
      smartExplanationText = incomingOrder.smart_reason;
    } else if (agent?.last_decision.reason && agent.last_decision.reason !== 'Waiting for offers') {
      smartExplanationText = agent.last_decision.reason;
    } else {
      smartExplanationText = 'Evaluating dynamic reservation wage and market conditions.';
    }
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden flex flex-col h-full">
      {/* Column Title Header */}
      <div className={`px-4 py-3 border-b flex items-center justify-between ${
        isSmart ? 'bg-sky-50/70 border-sky-200' : 'bg-slate-50 border-slate-200'
      }`}>
        <div>
          <h2 className="text-base font-bold text-slate-900 m-0 tracking-tight flex items-center gap-1.5">
            <span>{title}</span>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase tracking-wider ${
              isSmart ? 'bg-sky-100 text-sky-800 border border-sky-300' : 'bg-slate-200 text-slate-700'
            }`}>
              {subtitle}
            </span>
          </h2>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-600 font-medium">
          <MapPin className="h-3.5 w-3.5 text-slate-400" />
          <span>Z{currentZone}: {getZoneName(currentZone)}</span>
        </div>
      </div>

      {/* Independent Map Container */}
      <div className="relative w-full h-[380px] bg-slate-100">
        <div ref={mapContainerRef} className="w-full h-full" />

        {/* Temporary Shock Banner over map */}
        {currentShock && (
          <div className="absolute top-2 left-2 right-2 z-[500] bg-amber-50/95 border border-amber-300 text-amber-900 text-xs px-3 py-1.5 rounded-lg shadow-sm flex items-center justify-between pointer-events-none">
            <span className="flex items-center gap-1.5 font-semibold">
              <AlertTriangle className="h-4 w-4 text-amber-600 flex-shrink-0" />
              <span>{currentShock.message}</span>
            </span>
            {isSmart && (
              <span className="text-[10px] bg-sky-100 text-sky-800 border border-sky-300 px-1.5 py-0.5 rounded font-bold">
                Rerouting active
              </span>
            )}
          </div>
        )}
      </div>

      {/* Information Panel Below the Map */}
      <div className="p-4 flex-1 flex flex-col justify-between gap-3 bg-white">
        {/* 4-Stat Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
          {/* Simulated Time */}
          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Time</span>
            <strong className="text-slate-900 font-mono text-sm block mt-0.5">{simTime}</strong>
          </div>

          {/* Net Earnings */}
          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Net Earnings</span>
            <strong className={`font-mono text-sm block mt-0.5 ${isSmart ? 'text-sky-700' : 'text-slate-900'}`}>
              ${(agent?.net_earnings_mxn ?? 0).toFixed(2)}
            </strong>
          </div>

          {/* Current Order */}
          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Current Order</span>
            <strong className="text-slate-900 font-mono text-xs block mt-0.5 truncate">
              {incomingOrder?.order_id || (agent?.active_orders?.[0]?.order_id) || 'Waiting...'}
            </strong>
          </div>

          {/* Decision */}
          <div className="bg-slate-50 p-2.5 rounded-lg border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-400 block tracking-wider">Decision</span>
            <div className="mt-0.5">
              <span className={`inline-block px-2 py-0.5 rounded text-xs font-bold font-mono ${
                decision === 'ACCEPT'
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-300'
                  : decision === 'SKIP'
                  ? 'bg-rose-100 text-rose-800 border border-rose-300'
                  : 'bg-slate-200 text-slate-600'
              }`}>
                {decision}
              </span>
            </div>
          </div>
        </div>

        {/* Specific Decision Policy Details */}
        {!isSmart && (
          <div className="text-xs text-slate-500 bg-slate-50 px-3 py-2 rounded-lg border border-slate-200 flex items-center justify-between">
            <div className="truncate">
              <span className="font-semibold text-slate-700">Policy: </span>
              <span>{baselineReasonText}</span>
            </div>
            <span className="text-[11px] font-mono text-slate-400">
              Dist: {(agent?.distance_traveled_km ?? 0).toFixed(1)} km
            </span>
          </div>
        )}

        {/* Smart Agent "Why?" Explanation Box */}
        {isSmart && (
          <div className="bg-sky-50/60 border border-sky-200 rounded-lg p-3 text-xs">
            <div className="flex items-center justify-between mb-1">
              <span className="font-bold text-sky-900 flex items-center gap-1">
                <HelpCircle className="h-3.5 w-3.5 text-sky-600" />
                <span>Why?</span>
              </span>
              {incomingOrder && onInspectOrder && (
                <button
                  onClick={() => onInspectOrder(incomingOrder.order_id)}
                  className="text-[11px] text-sky-700 hover:text-sky-900 font-semibold underline cursor-pointer"
                >
                  View full economics
                </button>
              )}
            </div>
            <p className="text-slate-700 m-0 leading-relaxed font-sans text-xs">
              {smartExplanationText}
            </p>
            <div className="mt-2 pt-1.5 border-t border-sky-200/60 flex items-center justify-between text-[11px] text-slate-500 font-mono">
              <span>Reservation Wage: $125.00/hr</span>
              <span>Dist: {(agent?.distance_traveled_km ?? 0).toFixed(1)} km</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
