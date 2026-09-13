export interface MonterreyZoneInfo {
  id: number;
  name: string;
  shortName: string;
  municipality: string;
  lat: number;
  lng: number;
  radiusMeters: number;
  color: string;
  description: string;
}

export const MONTERREY_METRO_CENTER: [number, number] = [25.6850, -100.3200];
export const DEFAULT_MAP_ZOOM = 12;

/**
 * 12 Monterrey zones aligned with config/monterrey_zones.json
 */
export const MONTERREY_ZONES: Record<number, MonterreyZoneInfo> = {
  1: {
    id: 1,
    name: "Centro / Macroplaza",
    shortName: "Centro",
    municipality: "Monterrey",
    lat: 25.6692,
    lng: -100.3099,
    radiusMeters: 1600,
    color: "#64748b",
    description: "Macroplaza, Barrio Antiguo y zona comercial central",
  },
  2: {
    id: 2,
    name: "San Pedro Centro",
    shortName: "San Pedro",
    municipality: "San Pedro Garza García",
    lat: 25.6573,
    lng: -100.4023,
    radiusMeters: 1800,
    color: "#64748b",
    description: "Casco histórico y calzadas residenciales",
  },
  3: {
    id: 3,
    name: "Valle Oriente",
    shortName: "Valle Oriente",
    municipality: "San Pedro Garza García",
    lat: 25.6475,
    lng: -100.3355,
    radiusMeters: 1700,
    color: "#64748b",
    description: "Distrito financiero y plazas comerciales de alto consumo",
  },
  4: {
    id: 4,
    name: "Obispado",
    shortName: "Obispado",
    municipality: "Monterrey",
    lat: 25.6750,
    lng: -100.3450,
    radiusMeters: 1500,
    color: "#64748b",
    description: "Corredor médico, corporativos y zona residencial tradicional",
  },
  5: {
    id: 5,
    name: "Mitras Centro",
    shortName: "Mitras",
    municipality: "Monterrey",
    lat: 25.7040,
    lng: -100.3500,
    radiusMeters: 1600,
    color: "#64748b",
    description: "Área médica UANL y avenidas principales Gonzalitos",
  },
  6: {
    id: 6,
    name: "Cumbres",
    shortName: "Cumbres",
    municipality: "Monterrey",
    lat: 25.7270,
    lng: -100.3900,
    radiusMeters: 2200,
    color: "#64748b",
    description: "Corredor residencial poniente sobre Paseo de los Leones",
  },
  7: {
    id: 7,
    name: "Tecnológico",
    shortName: "Tecnológico",
    municipality: "Monterrey",
    lat: 25.6510,
    lng: -100.2890,
    radiusMeters: 1600,
    color: "#64748b",
    description: "Campus ITESM, alta densidad gastronómica y estudiantil",
  },
  8: {
    id: 8,
    name: "Contry",
    shortName: "Contry",
    municipality: "Monterrey",
    lat: 25.6280,
    lng: -100.2780,
    radiusMeters: 1600,
    color: "#64748b",
    description: "Zona sur residencial y comercial sobre Av. Garza Sada",
  },
  9: {
    id: 9,
    name: "Guadalupe Centro",
    shortName: "Guadalupe",
    municipality: "Guadalupe",
    lat: 25.6775,
    lng: -100.2597,
    radiusMeters: 1800,
    color: "#64748b",
    description: "Centro histórico de Guadalupe y corredor oriente",
  },
  10: {
    id: 10,
    name: "San Nicolás Centro",
    shortName: "San Nicolás",
    municipality: "San Nicolás de los Garza",
    lat: 25.7520,
    lng: -100.2950,
    radiusMeters: 1900,
    color: "#64748b",
    description: "Ciudad Universitaria UANL y zona centro norte",
  },
  11: {
    id: 11,
    name: "Apodaca Centro",
    shortName: "Apodaca",
    municipality: "Apodaca",
    lat: 25.7810,
    lng: -100.1880,
    radiusMeters: 2400,
    color: "#64748b",
    description: "Parques industriales y crecimiento suburbano noreste",
  },
  12: {
    id: 12,
    name: "Santa Catarina Centro",
    shortName: "Santa Catarina",
    municipality: "Santa Catarina",
    lat: 25.6730,
    lng: -100.4580,
    radiusMeters: 2200,
    color: "#64748b",
    description: "Acceso poniente a la metrópoli y zonas industriales",
  },
};

export function getZoneCenter(zoneId: number): [number, number] {
  const z = MONTERREY_ZONES[zoneId] || MONTERREY_ZONES[7];
  return [z.lat, z.lng];
}

export function getZoneName(zoneId: number): string {
  return MONTERREY_ZONES[zoneId]?.shortName || `Zona ${zoneId}`;
}

export function getZoneFullName(zoneId: number): string {
  return MONTERREY_ZONES[zoneId]?.name || `Zona ${zoneId}`;
}

export function getCourierCoordinates(
  zoneId: number,
  type: 'baseline' | 'smart' | 'pickup' | 'dropoff',
  _status?: string,
  _targetZone?: number
): [number, number] {
  const [lat, lng] = getZoneCenter(zoneId);
  switch (type) {
    case 'baseline':
      return [lat - 0.0035, lng - 0.0045];
    case 'smart':
      return [lat + 0.0035, lng + 0.0045];
    case 'pickup':
      return [lat + 0.004, lng - 0.003];
    case 'dropoff':
      return [lat - 0.004, lng + 0.004];
    default:
      return [lat, lng];
  }
}
