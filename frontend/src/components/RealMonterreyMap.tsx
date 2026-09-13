import React, { useEffect, useRef, useState } from 'react';
import L from 'leaflet';
import type { AgentState, IncomingOrderInfo, ShockReactionInfo } from '../types';
import { MONTERREY_METRO_CENTER, DEFAULT_MAP_ZOOM, MONTERREY_ZONES, getZoneCenter, getCourierCoordinates } from '../monterreyGeo';
import { Layers, Crosshair, CloudRain, Zap, AlertCircle } from 'lucide-react';

interface RealMonterreyMapProps {
  baseline: AgentState | null;
  smart: AgentState | null;
  incomingOrder: IncomingOrderInfo | null;
  currentShock: { type: string; duration_min: number; remaining_min?: number; zone?: number; multiplier?: number } | null;
  latestReaction: ShockReactionInfo | null;
  onInspectOrder?: (orderId: string) => void;
}

type TileStyle = 'dark' | 'voyager' | 'osm';

export const RealMonterreyMap: React.FC<RealMonterreyMapProps> = ({
  baseline,
  smart,
  incomingOrder,
  currentShock,
  onInspectOrder,
}) => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstanceRef = useRef<L.Map | null>(null);
  const tileLayerRef = useRef<L.TileLayer | null>(null);

  // Markers and layers refs
  const zonesLayerGroupRef = useRef<L.LayerGroup | null>(null);
  const baselineMarkerRef = useRef<L.Marker | null>(null);
  const smartMarkerRef = useRef<L.Marker | null>(null);
  const pickupMarkerRef = useRef<L.Marker | null>(null);
  const dropoffMarkerRef = useRef<L.Marker | null>(null);
  const routePolylineRef = useRef<L.Polyline | null>(null);
  const baselineRouteLineRef = useRef<L.Polyline | null>(null);
  const smartRouteLineRef = useRef<L.Polyline | null>(null);

  const [tileStyle, setTileStyle] = useState<TileStyle>('dark');
  const [showZoneCircles, setShowZoneCircles] = useState(true);

  const getTileUrl = (style: TileStyle) => {
    switch (style) {
      case 'dark':
        return 'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png';
      case 'voyager':
        return 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png';
      case 'osm':
        return 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
    }
  };

  // 1. Initialize Map
  useEffect(() => {
    if (!mapContainerRef.current || mapInstanceRef.current) return;

    const map = L.map(mapContainerRef.current, {
      center: MONTERREY_METRO_CENTER,
      zoom: DEFAULT_MAP_ZOOM,
      zoomControl: false,
      attributionControl: false,
    });

    L.control.zoom({ position: 'bottomright' }).addTo(map);

    const tileLayer = L.tileLayer(getTileUrl('dark'), {
      maxZoom: 18,
      subdomains: 'abcd',
    }).addTo(map);

    tileLayerRef.current = tileLayer;

    // Layer group for zones
    const zonesGroup = L.layerGroup().addTo(map);
    zonesLayerGroupRef.current = zonesGroup;

    mapInstanceRef.current = map;

    return () => {
      map.remove();
      mapInstanceRef.current = null;
    };
  }, []);

  // 2. Handle Tile Layer Switch
  useEffect(() => {
    if (!mapInstanceRef.current || !tileLayerRef.current) return;
    mapInstanceRef.current.removeLayer(tileLayerRef.current);
    const newLayer = L.tileLayer(getTileUrl(tileStyle), {
      maxZoom: 18,
      subdomains: tileStyle === 'osm' ? 'abc' : 'abcd',
    }).addTo(mapInstanceRef.current);
    tileLayerRef.current = newLayer;
  }, [tileStyle]);

  // 3. Render Monterrey Zone Polygons/Circles
  useEffect(() => {
    const group = zonesLayerGroupRef.current;
    if (!group) return;

    group.clearLayers();

    if (!showZoneCircles) return;

    const surgeZone = currentShock?.type === 'surge' ? currentShock.zone : null;

    Object.values(MONTERREY_ZONES).forEach((zone) => {
      const isSurge = surgeZone === zone.id;
      const isPickup = incomingOrder?.zone_pickup === zone.id;
      const isDropoff = incomingOrder?.zone_dropoff === zone.id;
      const hasBaseline = baseline?.current_zone === zone.id;
      const hasSmart = smart?.current_zone === zone.id;

      let borderColor = isSurge ? '#f59e0b' : zone.color;
      let fillColor = isSurge ? '#f59e0b' : zone.color;
      let fillOpacity = isSurge ? 0.35 : 0.08;
      let weight = isSurge ? 3 : 1.5;

      if (isPickup) {
        borderColor = '#10b981';
        fillColor = '#10b981';
        fillOpacity = 0.25;
        weight = 2.5;
      } else if (isDropoff) {
        borderColor = '#ef4444';
        fillColor = '#ef4444';
        fillOpacity = 0.25;
        weight = 2.5;
      }

      // Zone boundary circle
      const circle = L.circle([zone.lat, zone.lng], {
        radius: zone.radiusMeters,
        color: borderColor,
        fillColor: fillColor,
        fillOpacity: fillOpacity,
        weight: weight,
        dashArray: isSurge ? '4, 4' : undefined,
      });

      // Zone Center Label
      const labelIcon = L.divIcon({
        className: 'zone-label-marker',
        html: `
          <div style="
            background: rgba(15, 23, 42, 0.85);
            border: 1px solid ${borderColor};
            color: #f1f5f9;
            padding: 2px 7px;
            border-radius: 6px;
            font-size: 10px;
            font-weight: 700;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 4px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.5);
            pointer-events: auto;
            cursor: pointer;
            backdrop-filter: blur(4px);
          ">
            <span style="color: ${borderColor}; font-weight: 900;">Z${zone.id}</span>
            <span>${zone.shortName}</span>
            ${isSurge ? '<span style="color:#fbbf24;font-size:9px;">🔥' + (currentShock?.multiplier || 1.5) + 'x</span>' : ''}
          </div>
        `,
        iconSize: [120, 24],
        iconAnchor: [60, 12],
      });

      const labelMarker = L.marker([zone.lat, zone.lng], {
        icon: labelIcon,
        interactive: true,
      });

      const popupContent = `
        <div style="padding: 6px; min-width: 180px; font-family: inherit;">
          <div style="font-weight: 800; font-size: 13px; color: #f8fafc; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">
            Zona ${zone.id}: ${zone.name}
          </div>
          <div style="font-size: 11px; color: #94a3b8; margin-bottom: 6px;">
            ${zone.description}
          </div>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 10px;">
            <div style="background: #1e293b; padding: 4px 6px; border-radius: 4px;">
              <span style="color: #64748b; display: block;">Municipio</span>
              <strong style="color: #e2e8f0;">${zone.municipality}</strong>
            </div>
            <div style="background: #1e293b; padding: 4px 6px; border-radius: 4px;">
              <span style="color: #64748b; display: block;">Surge</span>
              <strong style="color: ${isSurge ? '#f59e0b' : '#10b981'};">${isSurge ? currentShock?.multiplier + 'x 🔥' : '1.0x (Normal)'}</strong>
            </div>
          </div>
          <div style="margin-top: 6px; font-size: 10px; color: #cbd5e1;">
            ${hasBaseline ? '🔵 <span style="color:#60a5fa; font-weight:600;">Baseline presente</span><br/>' : ''}
            ${hasSmart ? '🟣 <span style="color:#c084fc; font-weight:600;">SmartAgent presente</span>' : ''}
          </div>
        </div>
      `;

      labelMarker.bindPopup(popupContent);
      circle.bindPopup(popupContent);

      group.addLayer(circle);
      group.addLayer(labelMarker);
    });
  }, [showZoneCircles, currentShock, incomingOrder, baseline?.current_zone, smart?.current_zone]);

  // 4. Update Couriers on Map (Baseline & SmartAgent)
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    // A. Baseline Courier Marker
    const bZone = baseline?.current_zone ?? 7;
    const bTarget = incomingOrder?.zone_dropoff;
    const [bLat, bLng] = getCourierCoordinates(bZone, 'baseline', baseline?.status, bTarget);

    const bHtml = `
      <div class="pulse-baseline" style="
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: linear-gradient(135deg, #1d4ed8, #3b82f6);
        border: 2.5px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        box-shadow: 0 4px 14px rgba(37, 99, 235, 0.7);
        cursor: pointer;
        position: relative;
      ">
        <span style="font-size: 17px;">🛵</span>
        <div style="
          position: absolute;
          bottom: -18px;
          background: #1e3a8a;
          color: #bfdbfe;
          font-size: 9px;
          font-weight: 800;
          padding: 1px 5px;
          border-radius: 4px;
          white-space: nowrap;
          border: 1px solid #3b82f6;
          box-shadow: 0 2px 4px rgba(0,0,0,0.5);
        ">
          Baseline $${(baseline?.net_earnings_mxn ?? 0).toFixed(0)}
        </div>
      </div>
    `;

    const bIcon = L.divIcon({
      className: 'courier-marker-baseline',
      html: bHtml,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });

    if (!baselineMarkerRef.current) {
      baselineMarkerRef.current = L.marker([bLat, bLng], { icon: bIcon, zIndexOffset: 800 }).addTo(map);
    } else {
      baselineMarkerRef.current.setLatLng([bLat, bLng]);
      baselineMarkerRef.current.setIcon(bIcon);
    }

    const bPopup = `
      <div style="padding: 6px; min-width: 170px; font-family: inherit;">
        <div style="font-weight: 800; font-size: 12px; color: #60a5fa; border-bottom: 1px solid #1e3a8a; padding-bottom: 3px; margin-bottom: 5px;">
          🛵 FirstNearbyOrderBaseline
        </div>
        <div style="font-size: 11px; line-height: 1.5; color: #cbd5e1;">
          <strong>Zona actual:</strong> Zona ${bZone} (${MONTERREY_ZONES[bZone]?.shortName})<br/>
          <strong>Estado:</strong> <span style="color:#93c5fd;">${baseline?.status || 'idle'}</span><br/>
          <strong>Ganancia neta:</strong> $${(baseline?.net_earnings_mxn ?? 0).toFixed(2)} MXN<br/>
          <strong>Distancia:</strong> ${(baseline?.distance_traveled_km ?? 0).toFixed(1)} km<br/>
          <strong>Órdenes completadas:</strong> ${baseline?.orders_completed ?? 0}
        </div>
      </div>
    `;
    baselineMarkerRef.current.bindPopup(bPopup);

    // B. SmartAgent Courier Marker
    const sZone = smart?.current_zone ?? 7;
    const sTarget = incomingOrder?.zone_dropoff;
    const [sLat, sLng] = getCourierCoordinates(sZone, 'smart', smart?.status, sTarget);

    const sHtml = `
      <div class="pulse-smart" style="
        width: 38px;
        height: 38px;
        border-radius: 50%;
        background: linear-gradient(135deg, #7e22ce, #a855f7);
        border: 2.5px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        color: white;
        box-shadow: 0 4px 14px rgba(168, 85, 247, 0.7);
        cursor: pointer;
        position: relative;
      ">
        <span style="font-size: 17px;">⚡</span>
        <div style="
          position: absolute;
          bottom: -18px;
          background: #581c87;
          color: #f3e8ff;
          font-size: 9px;
          font-weight: 800;
          padding: 1px 5px;
          border-radius: 4px;
          white-space: nowrap;
          border: 1px solid #a855f7;
          box-shadow: 0 2px 4px rgba(0,0,0,0.5);
        ">
          Smart $${(smart?.net_earnings_mxn ?? 0).toFixed(0)}
        </div>
      </div>
    `;

    const sIcon = L.divIcon({
      className: 'courier-marker-smart',
      html: sHtml,
      iconSize: [38, 38],
      iconAnchor: [19, 19],
    });

    if (!smartMarkerRef.current) {
      smartMarkerRef.current = L.marker([sLat, sLng], { icon: sIcon, zIndexOffset: 900 }).addTo(map);
    } else {
      smartMarkerRef.current.setLatLng([sLat, sLng]);
      smartMarkerRef.current.setIcon(sIcon);
    }

    const sPopup = `
      <div style="padding: 6px; min-width: 170px; font-family: inherit;">
        <div style="font-weight: 800; font-size: 12px; color: #c084fc; border-bottom: 1px solid #6b21a8; padding-bottom: 3px; margin-bottom: 5px;">
          ⚡ SmartAgent (Estratégico)
        </div>
        <div style="font-size: 11px; line-height: 1.5; color: #cbd5e1;">
          <strong>Zona actual:</strong> Zona ${sZone} (${MONTERREY_ZONES[sZone]?.shortName})<br/>
          <strong>Estado:</strong> <span style="color:#d8b4fe;">${smart?.status || 'idle'}</span><br/>
          <strong>Ganancia neta:</strong> $${(smart?.net_earnings_mxn ?? 0).toFixed(2)} MXN<br/>
          <strong>Distancia:</strong> ${(smart?.distance_traveled_km ?? 0).toFixed(1)} km<br/>
          <strong>Salario Reserva:</strong> $125.00 MXN/h<br/>
          <strong>Órdenes completadas:</strong> ${smart?.orders_completed ?? 0}
        </div>
      </div>
    `;
    smartMarkerRef.current.bindPopup(sPopup);
  }, [baseline, smart, incomingOrder]);

  // 5. Update Incoming Order Delivery Route and Pickup/Dropoff Markers
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;

    if (!incomingOrder) {
      // Clear order layers
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
      if (baselineRouteLineRef.current) {
        map.removeLayer(baselineRouteLineRef.current);
        baselineRouteLineRef.current = null;
      }
      if (smartRouteLineRef.current) {
        map.removeLayer(smartRouteLineRef.current);
        smartRouteLineRef.current = null;
      }
      return;
    }

    const pCoords = getCourierCoordinates(incomingOrder.zone_pickup, 'pickup');
    const dCoords = getCourierCoordinates(incomingOrder.zone_dropoff, 'dropoff');

    // Pickup Marker (Store / Restaurant)
    const pickupHtml = `
      <div style="
        width: 34px;
        height: 34px;
        border-radius: 50%;
        background: #059669;
        border: 2px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 16px rgba(16, 185, 129, 0.9);
        cursor: pointer;
        position: relative;
      ">
        <span style="font-size: 16px;">🍴</span>
        <div style="
          position: absolute;
          top: -18px;
          background: #064e3b;
          color: #a7f3d0;
          font-size: 8px;
          font-weight: 800;
          padding: 1px 4px;
          border-radius: 4px;
          white-space: nowrap;
          border: 1px solid #10b981;
        ">
          Pickup Z${incomingOrder.zone_pickup}
        </div>
      </div>
    `;

    const pickupIcon = L.divIcon({
      className: 'pickup-order-marker',
      html: pickupHtml,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
    });

    if (!pickupMarkerRef.current) {
      pickupMarkerRef.current = L.marker(pCoords, { icon: pickupIcon, zIndexOffset: 700 }).addTo(map);
    } else {
      pickupMarkerRef.current.setLatLng(pCoords);
      pickupMarkerRef.current.setIcon(pickupIcon);
    }

    // Dropoff Marker (Customer Pin)
    const dropoffHtml = `
      <div style="
        width: 34px;
        height: 34px;
        border-radius: 50%;
        background: #dc2626;
        border: 2px solid #ffffff;
        display: flex;
        align-items: center;
        justify-content: center;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.9);
        cursor: pointer;
        position: relative;
      ">
        <span style="font-size: 16px;">📍</span>
        <div style="
          position: absolute;
          top: -18px;
          background: #7f1d1d;
          color: #fecaca;
          font-size: 8px;
          font-weight: 800;
          padding: 1px 4px;
          border-radius: 4px;
          white-space: nowrap;
          border: 1px solid #ef4444;
        ">
          Dropoff Z${incomingOrder.zone_dropoff}
        </div>
      </div>
    `;

    const dropoffIcon = L.divIcon({
      className: 'dropoff-order-marker',
      html: dropoffHtml,
      iconSize: [34, 34],
      iconAnchor: [17, 17],
    });

    if (!dropoffMarkerRef.current) {
      dropoffMarkerRef.current = L.marker(dCoords, { icon: dropoffIcon, zIndexOffset: 700 }).addTo(map);
    } else {
      dropoffMarkerRef.current.setLatLng(dCoords);
      dropoffMarkerRef.current.setIcon(dropoffIcon);
    }

    const totalPay = incomingOrder.base_pay_mxn * incomingOrder.surge_multiplier + incomingOrder.est_tip_mxn;
    const orderPopup = `
      <div style="padding: 6px; min-width: 190px; font-family: inherit;">
        <div style="font-weight: 800; font-size: 12px; color: #f59e0b; border-bottom: 1px solid #475569; padding-bottom: 3px; margin-bottom: 5px;">
          📦 ${incomingOrder.order_id}
        </div>
        <div style="font-size: 11px; line-height: 1.5; color: #cbd5e1;">
          <strong>Ruta:</strong> Zona ${incomingOrder.zone_pickup} ➔ Zona ${incomingOrder.zone_dropoff}<br/>
          <strong>Distancia total:</strong> ${incomingOrder.distance_total_km.toFixed(1)} km<br/>
          <strong>Pago ofrecido:</strong> <strong style="color:#10b981;">$${totalPay.toFixed(2)} MXN</strong><br/>
          <strong>Baseline:</strong> ${incomingOrder.baseline_decision}<br/>
          <strong>SmartAgent:</strong> ${incomingOrder.smart_decision}
        </div>
      </div>
    `;
    pickupMarkerRef.current.bindPopup(orderPopup);
    dropoffMarkerRef.current.bindPopup(orderPopup);

    // Route Polyline connecting Pickup ➔ Dropoff
    if (!routePolylineRef.current) {
      routePolylineRef.current = L.polyline([pCoords, dCoords], {
        color: '#10b981',
        weight: 4,
        opacity: 0.85,
        dashArray: '8, 8',
      }).addTo(map);
    } else {
      routePolylineRef.current.setLatLngs([pCoords, dCoords]);
    }
  }, [incomingOrder]);

  // Map Controls Handlers
  const handleCenterOnMonterrey = () => {
    mapInstanceRef.current?.setView(MONTERREY_METRO_CENTER, DEFAULT_MAP_ZOOM, { animate: true });
  };

  const handleCenterOnSmart = () => {
    if (!smart) return;
    const coords = getZoneCenter(smart.current_zone);
    mapInstanceRef.current?.setView(coords, 14, { animate: true });
  };

  const handleCenterOnBaseline = () => {
    if (!baseline) return;
    const coords = getZoneCenter(baseline.current_zone);
    mapInstanceRef.current?.setView(coords, 14, { animate: true });
  };

  const handleFitOrder = () => {
    if (!incomingOrder || !mapInstanceRef.current) return;
    const p = getZoneCenter(incomingOrder.zone_pickup);
    const d = getZoneCenter(incomingOrder.zone_dropoff);
    const bounds = L.latLngBounds([p, d]);
    mapInstanceRef.current.fitBounds(bounds, { padding: [60, 60], animate: true });
  };

  return (
    <div className="relative w-full h-full min-h-[480px] bg-gray-950 rounded-2xl overflow-hidden border border-gray-800 shadow-2xl flex flex-col">
      {/* Top Map Control Bar */}
      <div className="absolute top-3 left-3 z-[1000] flex flex-wrap items-center gap-2 pointer-events-auto">
        <div className="bg-gray-900/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-gray-700/70 shadow-lg flex items-center gap-2 text-xs">
          <span className="font-bold text-gray-200 flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping inline-block" />
            <span>Despacho Monterrey (12 Zonas)</span>
          </span>
          <span className="text-gray-500">|</span>
          <button
            onClick={() => setTileStyle(tileStyle === 'dark' ? 'voyager' : tileStyle === 'voyager' ? 'osm' : 'dark')}
            className="flex items-center gap-1 text-[11px] font-semibold text-gray-300 hover:text-white px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 transition cursor-pointer"
            title="Cambiar capa visual de mapa"
          >
            <Layers className="h-3.5 w-3.5 text-blue-400" />
            <span className="capitalize">{tileStyle}</span>
          </button>
          <button
            onClick={() => setShowZoneCircles(!showZoneCircles)}
            className={`text-[11px] font-semibold px-2 py-0.5 rounded transition cursor-pointer ${
              showZoneCircles ? 'bg-purple-950/80 text-purple-300 border border-purple-800' : 'bg-gray-800 text-gray-400'
            }`}
          >
            Zonas
          </button>
        </div>

        {/* Shock Badge on Map */}
        {currentShock && (
          <div className="bg-amber-950/90 backdrop-blur-md px-3 py-1.5 rounded-xl border border-amber-500/60 shadow-lg flex items-center gap-2 text-xs text-amber-200 animate-pulse">
            {currentShock.type === 'rain' ? <CloudRain className="h-4 w-4 text-cyan-400" /> : <Zap className="h-4 w-4 text-amber-400" />}
            <span className="font-bold uppercase text-[11px]">{currentShock.type} ACTIVO</span>
            {currentShock.zone && <span>Zona {currentShock.zone} ({currentShock.multiplier}x)</span>}
          </div>
        )}
      </div>

      {/* Quick Navigation Controls */}
      <div className="absolute top-3 right-3 z-[1000] flex flex-col gap-1.5 pointer-events-auto">
        <button
          onClick={handleCenterOnMonterrey}
          className="bg-gray-900/90 hover:bg-gray-800 backdrop-blur-md p-2 rounded-lg border border-gray-700 shadow text-xs text-gray-300 hover:text-white flex items-center gap-1.5 transition cursor-pointer"
          title="Centrar en Monterrey Metropolitano"
        >
          <Crosshair className="h-4 w-4 text-emerald-400" />
          <span className="text-[10px] font-semibold hidden sm:inline">Monterrey</span>
        </button>
        <button
          onClick={handleCenterOnSmart}
          className="bg-gray-900/90 hover:bg-gray-800 backdrop-blur-md px-2 py-1.5 rounded-lg border border-purple-700/60 shadow text-[10px] font-semibold text-purple-300 hover:text-purple-100 flex items-center gap-1.5 transition cursor-pointer"
          title="Centrar en SmartAgent"
        >
          <span>⚡ Smart</span>
        </button>
        <button
          onClick={handleCenterOnBaseline}
          className="bg-gray-900/90 hover:bg-gray-800 backdrop-blur-md px-2 py-1.5 rounded-lg border border-blue-700/60 shadow text-[10px] font-semibold text-blue-300 hover:text-blue-100 flex items-center gap-1.5 transition cursor-pointer"
          title="Centrar en Baseline"
        >
          <span>🛵 Baseline</span>
        </button>
        {incomingOrder && (
          <button
            onClick={handleFitOrder}
            className="bg-emerald-950/90 hover:bg-emerald-900 backdrop-blur-md px-2 py-1.5 rounded-lg border border-emerald-500 shadow text-[10px] font-bold text-emerald-300 hover:text-emerald-100 flex items-center gap-1.5 transition cursor-pointer animate-bounce"
            title="Ver orden activa en mapa"
          >
            <span>📦 Ver Orden</span>
          </button>
        )}
      </div>

      {/* Floating Active Order Dispatch Card (Over Map) */}
      {incomingOrder && (
        <div className="absolute bottom-4 left-4 right-4 sm:right-auto sm:max-w-md z-[1000] bg-gray-900/95 backdrop-blur-lg border border-emerald-500/50 rounded-2xl p-3.5 shadow-2xl pointer-events-auto">
          <div className="flex items-center justify-between border-b border-gray-800 pb-2 mb-2">
            <div className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
              <strong className="text-white text-xs font-mono">{incomingOrder.order_id}</strong>
              <span className="text-[10px] text-gray-400">
                Z{incomingOrder.zone_pickup} ({MONTERREY_ZONES[incomingOrder.zone_pickup]?.shortName}) ➔ Z{incomingOrder.zone_dropoff} ({MONTERREY_ZONES[incomingOrder.zone_dropoff]?.shortName})
              </span>
            </div>
            <strong className="text-emerald-400 text-sm font-mono">
              ${(incomingOrder.base_pay_mxn * incomingOrder.surge_multiplier + incomingOrder.est_tip_mxn).toFixed(2)} MXN
            </strong>
          </div>

          <div className="grid grid-cols-2 gap-2 text-xs mb-2">
            <div className={`p-2 rounded-lg border ${
              incomingOrder.baseline_decision === 'ACCEPT'
                ? 'bg-blue-950/40 border-blue-800 text-blue-300'
                : 'bg-gray-950 border-gray-800 text-gray-400'
            }`}>
              <div className="text-[10px] uppercase font-bold text-blue-400">Baseline</div>
              <div className="font-mono font-bold text-sm">{incomingOrder.baseline_decision}</div>
              <div className="text-[10px] text-gray-400">Dist: {incomingOrder.distance_pickup_km.toFixed(1)} km</div>
            </div>

            <div className={`p-2 rounded-lg border ${
              incomingOrder.smart_decision === 'ACCEPT'
                ? 'bg-purple-950/40 border-purple-700 text-purple-300'
                : 'bg-amber-950/40 border-amber-800 text-amber-300'
            }`}>
              <div className="text-[10px] uppercase font-bold text-purple-400">SmartAgent</div>
              <div className="font-mono font-bold text-sm">{incomingOrder.smart_decision}</div>
              <div className="text-[10px] truncate text-amber-200/80">{incomingOrder.smart_reason}</div>
            </div>
          </div>

          {incomingOrder.is_disagreement && (
            <div className="flex items-center justify-between bg-amber-950/40 border border-amber-600/40 rounded-lg p-2 text-xs">
              <span className="text-amber-300 flex items-center gap-1 font-semibold text-[11px]">
                <AlertCircle className="h-3.5 w-3.5 text-amber-400" />
                Desacuerdo: Smart optimiza rentabilidad horaria
              </span>
              {onInspectOrder && (
                <button
                  onClick={() => onInspectOrder(incomingOrder.order_id)}
                  className="px-2 py-1 bg-amber-600 hover:bg-amber-500 text-black font-bold text-[10px] rounded transition cursor-pointer"
                >
                  Inspeccionar
                </button>
              )}
            </div>
          )}
        </div>
      )}

      {/* Map Canvas Container */}
      <div ref={mapContainerRef} className="w-full h-full min-h-[480px] z-0" />

      {/* Bottom Map Legend */}
      <div className="absolute bottom-2 right-2 z-[990] bg-gray-950/80 backdrop-blur-md px-3 py-1 rounded-md border border-gray-800 text-[10px] text-gray-400 flex items-center gap-3 pointer-events-none">
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Baseline</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-purple-500 inline-block" /> SmartAgent</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Pickup</span>
        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Dropoff</span>
      </div>
    </div>
  );
};
