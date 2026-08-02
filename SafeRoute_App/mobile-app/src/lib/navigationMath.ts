import type { LngLat } from "./types";

const EARTH_RADIUS_M = 6_371_000;

export function distanceMeters(a: LngLat, b: LngLat): number {
  const lat1 = (a[1] * Math.PI) / 180;
  const lat2 = (b[1] * Math.PI) / 180;
  const dLat = lat2 - lat1;
  const dLng = ((b[0] - a[0]) * Math.PI) / 180;
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

interface Projection { distanceFromRouteM: number; distanceAlongM: number; remainingM: number; segmentIndex: number; }

export function projectOnRoute(point: LngLat, coordinates: LngLat[]): Projection | null {
  if (coordinates.length < 2) return null;
  const originLat = (point[1] * Math.PI) / 180;
  const scaleX = (Math.PI / 180) * EARTH_RADIUS_M * Math.cos(originLat);
  const scaleY = (Math.PI / 180) * EARTH_RADIUS_M;
  const xy = ([lng, lat]: LngLat) => [(lng - point[0]) * scaleX, (lat - point[1]) * scaleY] as const;
  const segmentLengths = coordinates.slice(1).map((coordinate, index) => distanceMeters(coordinates[index], coordinate));
  const total = segmentLengths.reduce((sum, value) => sum + value, 0);
  let traversed = 0;
  let best = { distanceFromRouteM: Number.POSITIVE_INFINITY, distanceAlongM: 0, remainingM: total, segmentIndex: 0 };
  for (let index = 0; index < coordinates.length - 1; index += 1) {
    const [ax, ay] = xy(coordinates[index]); const [bx, by] = xy(coordinates[index + 1]);
    const dx = bx - ax; const dy = by - ay; const denom = dx * dx + dy * dy;
    const t = denom === 0 ? 0 : Math.max(0, Math.min(1, -(ax * dx + ay * dy) / denom));
    const px = ax + t * dx; const py = ay + t * dy;
    const distance = Math.hypot(px, py);
    const along = traversed + segmentLengths[index] * t;
    if (distance < best.distanceFromRouteM) best = { distanceFromRouteM: distance, distanceAlongM: along, remainingM: Math.max(0, total - along), segmentIndex: index };
    traversed += segmentLengths[index];
  }
  return best;
}
