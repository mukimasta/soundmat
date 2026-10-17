/** 看板上的小图形：半圆仪表、迷你曲线、分段条、电平表（样式取自设计稿）。 */

const C = { track: '#34312C', value: '#EDE8DF', tick: '#5A554C', red: '#E5553A' };

function arcPoint(frac: number, r: number): [number, number] {
  const a = Math.PI * (1 - frac);
  return [100 + r * Math.cos(a), 100 - r * Math.sin(a)];
}

function arc(f0: number, f1: number, r: number): string {
  const [x0, y0] = arcPoint(f0, r);
  const [x1, y1] = arcPoint(f1, r);
  return `M${x0.toFixed(2)} ${y0.toFixed(2)} A${r} ${r} 0 0 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/** 半圆仪表：value / max，红线标出上限 */
export function Gauge({ value, max, limit, label, text, width = '100%' }: {
  value: number | null; max: number; limit: number; label: string; text: string; width?: string | number;
}) {
  const f = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  const [mx1, my1] = arcPoint(limit / max, 70);
  const [mx2, my2] = arcPoint(limit / max, 92);
  return (
    <span style={{ position: 'relative', display: 'block', width, maxWidth: 220 }}>
      <svg width="100%" viewBox="0 0 200 112" role="img" aria-label={label} style={{ display: 'block' }}>
        <path d={arc(0, 1, 80)} fill="none" stroke={C.track} strokeWidth="12" />
        {f > 0 && <path d={arc(0, Math.max(f, 0.001), 80)} fill="none" stroke={C.value} strokeWidth="12" />}
        {Array.from({ length: 11 }, (_, i) => {
          const [x1, y1] = arcPoint(i / 10, 60);
          const [x2, y2] = arcPoint(i / 10, 66);
          return <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke={C.tick} strokeWidth="1.2" />;
        })}
        <line x1={mx1} y1={my1} x2={mx2} y2={my2} stroke={C.red} strokeWidth="3" strokeLinecap="round" />
      </svg>
      <span aria-hidden="true" className="gauge-text">{text}</span>
    </span>
  );
}

/** 最近一段时间的曲线 */
export function Spark({ values, max, height = 34 }: { values: number[]; max: number; height?: number }) {
  if (values.length < 2) return <svg width="100%" height={height} aria-hidden="true" />;
  const n = values.length;
  const pts = values.map((v, i) => `${((i / (n - 1)) * 300).toFixed(1)},${(44 - Math.min(1, v / max) * 40).toFixed(1)}`);
  return (
    <svg width="100%" height={height} viewBox="0 0 300 44" preserveAspectRatio="none" aria-hidden="true" style={{ display: 'block' }}>
      <path d={`M0,44 L${pts.join(' L')} L300,44 Z`} fill="rgba(237,232,223,0.08)" />
      <polyline points={pts.join(' ')} fill="none" stroke={C.value} strokeWidth="1.5" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/** 12 段的占用条 */
export function Segments({ frac, warn = 0.85 }: { frac: number | null; warn?: number }) {
  const lit = frac === null ? 0 : Math.round(Math.max(0, Math.min(1, frac)) * 12);
  return (
    <span className="segs" aria-hidden="true">
      {Array.from({ length: 12 }, (_, i) => (
        <span key={i} style={{ background: i < lit ? ((frac ?? 0) >= warn ? 'var(--amber)' : 'var(--text)') : 'var(--track)' }} />
      ))}
    </span>
  );
}

/** 输出电平表：每个声道一列，−60 到 0 dB */
export function VuMeter({ levels, names }: { levels: number[]; names: string[] }) {
  const segs = 20;
  const col = 25;
  const w = 18 + Math.max(1, levels.length) * col;
  return (
    <svg width={w} height="150" viewBox={`0 0 ${w} 150`} role="img"
      aria-label={`输出电平：${levels.map((l, i) => `${names[i] ?? i + 1} ${Math.round(l)} dB`).join('，')}`}>
      {[0, -12, -24, -36, -48, -60].map((d, i) => (
        <text key={d} x="15" y={7 + i * 28} fontSize="8" fill="#8F887C" textAnchor="end" dominantBaseline="middle" fontFamily="JetBrains Mono, monospace">{d}</text>
      ))}
      {levels.map((l, c) => {
        const lit = Math.round(Math.max(0, Math.min(1, (l + 60) / 60)) * segs);
        return Array.from({ length: segs }, (_, i) => (
          <rect key={`${c}-${i}`} x={20 + c * col} y={143 - i * 7} width="19" height="5" rx="1"
            fill={i < lit ? (i >= segs - 2 ? '#E5553A' : '#F5F0E6') : '#2E2B27'} />
        ));
      })}
    </svg>
  );
}
