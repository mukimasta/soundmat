import { memo, useMemo } from 'react';
import type { StoneMsg, Zone } from '../api/types';
import { LED_RADIUS, RING_COLORS, polar, sectorPath, zoneFill } from './geometry';

/** 压力达到满量程的一半时显示为最深的颜色（石头的读数通常远低于满量程） */
const DISPLAY_FULL = 0.5;

interface Props {
  geometry: Zone[];
  /** 每个区域的压力 0–1000；null 表示没有数据（已断开） */
  pressure: number[] | null;
  occupied: number[];
  /** 每颗石头的位置；有它时石头画在实际位置（骑在分界线上的画在线上），没有时画在主区中心 */
  stones?: StoneMsg[];
  ledCount: number;
  /** 灯环预览：十六进制字符串，每颗灯 6 个字符 rrggbb（逻辑顺序）；null 表示没有数据 */
  leds?: string | null;
  onZone?: (zone: number) => void;
}

function MatViewImpl({ geometry, pressure, occupied, stones: located, ledCount, leds, onZone }: Props) {
  const paths = useMemo(
    () => geometry.map((z) => ({ z, d: sectorPath(z.rInner, z.rOuter, z.center, z.span) })),
    [geometry],
  );
  const tappable = !!onZone;
  const stones = (located ?? occupied.map((zone, i) => ({ id: -1 - i, zone, r: 0, a: 0, s: 0 })))
    .filter((s) => geometry[s.zone])
    .map((s) => {
      const z = geometry[s.zone];
      const at = located ? polar(s.r, s.a) : polar((z.rInner + z.rOuter) / 2, z.center);
      return { key: s.id, zone: z, x: at[0], y: at[1] };
    });
  const label = pressure
    ? `垫面实时图：${stones.length} 颗石头，外圈是灯环预览`
    : '垫面：没有数据';

  return (
    <svg viewBox="-31 -31 62 62" role="img" aria-label={label}>
      <circle cx="0" cy="0" r={LED_RADIUS} fill="none" stroke="#1A1917" strokeWidth="2.8" />
      <circle cx="0" cy="0" r="27.6" fill="#0B0A09" />
      {paths.map(({ z, d }) => (
        <path
          key={z.index}
          d={d}
          data-zone={z.index}
          fill={zoneFill(pressure ? pressure[z.index] / 1000 / DISPLAY_FULL : 0, z.ring)}
          style={{ cursor: tappable ? 'pointer' : 'default' }}
          onClick={tappable ? () => onZone!(z.index) : undefined}
        />
      ))}
      {tappable && (
        <circle cx="0" cy="0" r="27.95" fill="none" stroke="#E9A23B" strokeOpacity="0.75"
          strokeWidth="0.12" strokeDasharray="0.55 0.45" pointerEvents="none" />
      )}
      {pressure && stones.map(({ key, zone: z, x, y }) => {
        const c = RING_COLORS[z.ring];
        const rot = Math.round((z.center * 1.7 + z.ring * 23) % 180);
        return (
          <g key={key} data-stone={z.index} transform={`translate(${x} ${y}) rotate(${rot})`} pointerEvents="none">
            <ellipse rx="2.0" ry="1.7" fill={`rgba(${c[0]},${c[1]},${c[2]},0.38)`} />
            <ellipse rx="1.22" ry="0.94" fill="#ECE6DB" />
            <ellipse cx="-0.32" cy="-0.28" rx="0.5" ry="0.26" fill="#FFFFFF" opacity="0.85" />
          </g>
        );
      })}
      <LedRing ledCount={ledCount} leds={leds ?? null} />
    </svg>
  );
}

export const MatView = memo(MatViewImpl);

/** 解码灯环预览：亮度过低的灯当作不亮 */
export function decodeLeds(hex: string | null, count: number): ([number, number, number] | null)[] {
  const out: ([number, number, number] | null)[] = new Array(count).fill(null);
  if (!hex) return out;
  for (let i = 0; i < count && i * 6 + 6 <= hex.length; i++) {
    const r = parseInt(hex.slice(i * 6, i * 6 + 2), 16);
    const g = parseInt(hex.slice(i * 6 + 2, i * 6 + 4), 16);
    const b = parseInt(hex.slice(i * 6 + 4, i * 6 + 6), 16);
    out[i] = Math.max(r, g, b) < 24 ? null : [r, g, b];
  }
  return out;
}

/**
 * 灯环预览单独成一个组件：它和灯光引擎同频刷新（60 次/秒），
 * 拆开后每帧只重画 108 颗灯，不连带重画 224 个区域。
 */
const LedRing = memo(function LedRing({ ledCount, leds }: { ledCount: number; leds: string | null }) {
  const ledPos = useMemo(
    () => Array.from({ length: ledCount }, (_, i) => polar(LED_RADIUS, (i * 360) / ledCount)),
    [ledCount],
  );
  const colors = decodeLeds(leds, ledCount);
  return (
    <g pointerEvents="none">
      {ledPos.map(([x, y], i) => {
        const c = colors[i];
        if (!c) return <circle key={i} cx={x} cy={y} r="0.34" fill="#2E2B26" />;
        const rgb = `${c[0]},${c[1]},${c[2]}`;
        const b = Math.max(c[0], c[1], c[2]) / 255;
        return (
          <g key={i}>
            <circle cx={x} cy={y} r={(0.8 + 0.6 * b).toFixed(2)} fill={`rgba(${rgb},${(0.5 * b * b).toFixed(2)})`} />
            <circle cx={x} cy={y} r="0.46" fill={`rgb(${rgb})`} />
          </g>
        );
      })}
    </g>
  );
});
