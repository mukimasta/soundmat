import { memo, useMemo } from 'react';
import type { Zone } from '../api/types';
import { LED_RADIUS, RING_COLORS, polar, sectorPath, zoneFill } from './geometry';

/** 压力达到满量程的一半时显示为最深的颜色（石头的读数通常远低于满量程） */
const DISPLAY_FULL = 0.5;

interface Props {
  geometry: Zone[];
  /** 每个区域的压力 0–1000；null 表示没有数据（已断开） */
  pressure: number[] | null;
  occupied: number[];
  ledCount: number;
  /** 灯环预览：每个逻辑位置的颜色 [r, g, b]，未亮为 null */
  leds?: ([number, number, number] | null)[] | null;
  onZone?: (zone: number) => void;
}

function MatViewImpl({ geometry, pressure, occupied, ledCount, leds, onZone }: Props) {
  const paths = useMemo(
    () => geometry.map((z) => ({ z, d: sectorPath(z.rInner, z.rOuter, z.center, z.span) })),
    [geometry],
  );
  const ledPos = useMemo(
    () => Array.from({ length: ledCount }, (_, i) => polar(LED_RADIUS, (i * 360) / ledCount)),
    [ledCount],
  );
  const tappable = !!onZone;
  const stones = occupied.map((i) => geometry[i]).filter(Boolean);
  const label = pressure
    ? `垫面实时图：${occupied.length} 个区域判断为有石头，外圈是灯环预览`
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
      {pressure && stones.map((z) => {
        const [x, y] = polar((z.rInner + z.rOuter) / 2, z.center);
        const c = RING_COLORS[z.ring];
        const rot = Math.round((z.center * 1.7 + z.ring * 23) % 180);
        return (
          <g key={z.index} data-stone={z.index} transform={`translate(${x} ${y}) rotate(${rot})`} pointerEvents="none">
            <ellipse rx="2.0" ry="1.7" fill={`rgba(${c[0]},${c[1]},${c[2]},0.38)`} />
            <ellipse rx="1.22" ry="0.94" fill="#ECE6DB" />
            <ellipse cx="-0.32" cy="-0.28" rx="0.5" ry="0.26" fill="#FFFFFF" opacity="0.85" />
          </g>
        );
      })}
      {ledPos.map(([x, y], i) => {
        const c = leds?.[i];
        if (!c || Math.max(c[0], c[1], c[2]) < 24) return <circle key={i} cx={x} cy={y} r="0.34" fill="#2E2B26" />;
        const rgb = `${c[0]},${c[1]},${c[2]}`;
        return (
          <g key={i} pointerEvents="none">
            <circle cx={x} cy={y} r="1.2" fill={`rgba(${rgb},0.45)`} />
            <circle cx={x} cy={y} r="0.46" fill={`rgb(${rgb})`} />
          </g>
        );
      })}
    </svg>
  );
}

export const MatView = memo(MatViewImpl);
