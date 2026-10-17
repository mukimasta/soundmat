import type { Levels } from '../api/selectors';
import { RING_COLORS } from './geometry';

/**
 * 每环的声音电平：左半边是左音箱，右半边是右音箱，环名写在右半边下面（设计稿）。
 * 没有电平数据（还没有合成器服务）时所有条都是零。
 */
export function RingMeters({ labels, levels }: { labels: string[]; levels: Levels | null }) {
  const rings = levels?.rings ?? [];
  const height = (db: number | undefined) => {
    if (db === undefined || db <= -60) return 0;
    return Math.max(0, Math.min(1, (db + 60) / 60)) * 46;
  };
  const playing = labels.filter((_, i) => height(rings[i]?.[0]) + height(rings[i]?.[1]) > 2);
  const aria = `每个环的声音电平，左半边是左音箱，右半边是右音箱。${playing.length ? `正在发声：${playing.join('、')}。` : '现在没有声音。'}`;
  return (
    <div className="meters" role="img" aria-label={aria}>
      <span className="axis" aria-hidden="true" />
      <span className="lr" style={{ left: -8 }} aria-hidden="true">L</span>
      <span className="lr" style={{ right: -8 }} aria-hidden="true">R</span>
      {Array.from({ length: 8 }, (_, ring) => [0, 1].map((side) => {
        const h = height(rings[ring]?.[side]);
        const left = `calc(${side === 0 ? 0 : 50}% + ${8 + ring * 20}px)`;
        const c = RING_COLORS[ring];
        return (
          <span key={`${ring}-${side}`} aria-hidden="true">
            <span className="bar" style={{ left, top: 50 - h, height: h }} />
            <span className="cap" style={{ left, top: 48 - h, background: `rgb(${c.join(',')})`, opacity: h > 0 ? 1 : 0.35 }} />
          </span>
        );
      }))}
      {labels.map((name, ring) => {
        const on = height(rings[ring]?.[0]) + height(rings[ring]?.[1]) > 2;
        return (
          <span key={ring} className="label" aria-hidden="true"
            style={{ left: `calc(50% + ${5 + ring * 20}px)`, color: on ? 'var(--text)' : 'var(--text-3)' }}>
            {Array.from(name).map((ch, i) => <span key={i}>{ch}</span>)}
          </span>
        );
      })}
    </div>
  );
}
