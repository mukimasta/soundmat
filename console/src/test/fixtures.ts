import type { HelloMsg, MatMsg, Zone } from '../api/types';

export function geometry(): Zone[] {
  const out: Zone[] = [];
  const centers = [4.0, 7.107, 10.2145, 13.3215, 16.4285, 19.5355, 22.643, 25.75];
  let index = 0;
  for (let ring = 0; ring < 8; ring++) {
    const n = ring < 2 ? 16 : 32;
    for (let slot = 0; slot < n; slot++) {
      const center = ring < 2 ? 2 * slot * 11.25 : slot * 11.25;
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

export const KYOTO = {
  id: 'kyoto', title: '京都岚山', mode: 'ambient', modeLabel: 'Ambient · 氛围',
  description: 'C 五声音阶。', ringLabels: ['低音', '低音', '和声', '竹林', '天气', '马林巴', '旋律', '铃声'],
  missing: ['a.wav', 'b.wav'], error: null,
};
export const LOFI = {
  id: 'lofi_1', title: 'Lo-Fi Loop · Progression 1', mode: 'jam', modeLabel: 'Jam · 合奏 · 120 BPM',
  description: '京都夜雨。', ringLabels: ['控制', '控制', '低音', '贝斯', '拨弦', '暗电钢', '电钢', '马林巴'],
  missing: [], error: null,
};

const placed = (labels: string[], from = 0) =>
  labels.slice(from).map((label, k) => ({ id: `placed.${k + from}`, label, group: 'placed', ring: k + from, color: null }));

export const KYOTO_METERS = placed(KYOTO.ringLabels);
export const LOFI_METERS = [
  { id: 'background.0', label: '和声', group: 'background', ring: null, color: null },
  { id: 'background.1', label: '鼓', group: 'background', ring: null, color: null },
  ...placed(LOFI.ringLabels, 2),
];

export function playingState(extra: Record<string, unknown> = {}) {
  return {
    status: {
      current: {
        virtual: true, arrangement: 'kyoto', mode: 'ambient',
        modeStatus: { text: '每环一层 · 左右两只音箱', reading: null, transport: null },
        meters: KYOTO_METERS,
      },
      log: [{ at: 1760000000, level: 'warning', text: '京都岚山：缺少 2 个声音素材，用到它们的声音不会发声' }],
    },
    catalog: { arrangements: [KYOTO, LOFI] },
    settings: {
      sound: { layout: { azimuths: [270, 90], names: ['左', '右'] }, orientation: 0, volume: 0.8 },
      run: { defaultArrangement: 'kyoto', soundLibrary: '/home/soundmat/sound' },
      recording: { path: '/home/soundmat/data/recordings', stems: true },
    },
    ...extra,
  };
}
