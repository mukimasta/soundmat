/** 编排的小图标：同心圆环加三颗石头；Jam 有一根扫描线。 */
export function ArrIcon({ mode, size = 54 }: { mode: string; size?: number }) {
  const dots: [number, number, number, string][] =
    mode === 'jam'
      ? [[-6.4, -11.1, 2.1, '#3098FF'], [12.4, 6.9, 2.1, '#FF6C20'], [-3.9, 7.9, 1.9, '#20BC94']]
      : [[7, -5.8, 2.1, '#3098FF'], [-11.6, 5.2, 2.1, '#FF6C20'], [2.2, 4.2, 1.9, '#20BC94']];
  const svg = Math.round(size * 0.78);
  return (
    <span className="arr-icon" style={{ width: size, height: size }}>
      <svg width={svg} height={svg} viewBox="-20 -20 40 40" aria-hidden="true">
        <circle r="17.5" fill="none" stroke="#FFF6E6" strokeOpacity="0.6" strokeWidth="1.4" strokeDasharray="0.5 2.2" strokeLinecap="round" />
        {[13.5, 9, 4.5].map((r) => <circle key={r} r={r} fill="none" stroke="#FFFFFF" strokeOpacity="0.16" strokeWidth="1" />)}
        {dots.map(([x, y, r, c]) => <circle key={c} cx={x} cy={y} r={r} fill={c} />)}
        {mode === 'jam' && <path d="M0 0 L0 -17" stroke="#FFFFFF" strokeWidth="1.4" strokeLinecap="round" opacity="0.9" />}
      </svg>
    </span>
  );
}
