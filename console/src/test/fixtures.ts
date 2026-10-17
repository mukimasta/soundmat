import type { HelloMsg, MatMsg, Zone } from '../api/types';

export function geometry(): Zone[] {
  const out: Zone[] = [];
  const centers = [4.0, 7.107, 10.2145, 13.3215, 16.4285, 19.5355, 22.643, 25.75];
  let index = 0;
  for (let ring = 0; ring < 8; ring++) {
    const n = ring < 2 ? 16 : 32;
    for (let slot = 0; slot < n; slot++) {
      const center = ring < 2 ? (2 * slot + 1) * 11.25 : slot * 11.25;
      out.push({ index, id: `${ring}:${slot}`, ring, slot, center: center % 360, span: 360 / n,
        rInner: centers[ring] - 1.375, rOuter: centers[ring] + 1.375 });
      index++;
    }
  }
  return out;
}

export function hello(state: Record<string, unknown> = {}): HelloMsg {
  return { type: 'hello', geometry: geometry(), config: [], ledCount: 108, state };
}

export function mat(occupied: number[], source: 'virtual' | 'controller' = 'virtual'): MatMsg {
  const pressure = new Array(224).fill(0);
  occupied.forEach((i) => (pressure[i] = 500));
  return { type: 'mat', t: 1, source, pressure, occupied, ringCounts: [0, 0, 0, 0, 0, 0, 0, 0], control: null };
}
