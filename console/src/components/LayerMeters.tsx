import type { Levels, MeterDef } from '../api/selectors';
import { RING_COLORS } from './geometry';

const MAX_H = 46;
const NEUTRAL = '#8A847A';

/**
 * 每一层声音的电平：一层一根条，名字写在条下面（CONSOLE「垫面」）。
 * 条按编排声明分成「背景」和「石头」两组，组之间只靠间距分开，不加标题。
 * 不分左右声道：方位由垫面上石头的位置表达，这里只回答“这一层有多响”。
 * 没有电平数据（还没有合成器服务）时所有条都是零。
 */
export function LayerMeters({ meters, levels }: { meters: MeterDef[]; levels: Levels | null }) {
  const values = levels?.meters ?? [];
  const height = (db: number | undefined) => {
    if (db === undefined || db <= -60) return 0;
    return Math.max(0, Math.min(1, (db + 60) / 60)) * MAX_H;
  };
  const playing = meters.filter((_, i) => height(values[i]) > 1).map((m) => m.label);
  const aria = `每一层声音的电平。${playing.length ? `正在发声：${playing.join('、')}。` : '现在没有声音。'}`;
  const groups = (['background', 'placed'] as const)
    .map((g) => meters.map((m, i) => ({ m, i })).filter(({ m }) => m.group === g))
    .filter((g) => g.length > 0);

  return (
    <div className="meters" role="img" aria-label={aria}>
      {groups.map((items, gi) => (
        <div key={gi} className="meter-group">
          {items.map(({ m, i }) => {
            const h = height(values[i]);
            const c = m.color ?? (m.ring !== null && m.ring !== undefined ? `rgb(${RING_COLORS[m.ring].join(',')})` : NEUTRAL);
            return (
              <div key={m.id} className="meter" data-meter={m.id} aria-hidden="true">
                <span className="well">
                  <span className="cap" style={{ bottom: h, background: c, opacity: h > 0 ? 1 : 0.35 }} />
                  <span className="bar" style={{ height: h }} />
                </span>
                <span className="label" style={{ color: h > 1 ? 'var(--text)' : 'var(--text-3)' }}>
                  {Array.from(m.label).map((ch, k) => <span key={k}>{ch}</span>)}
                </span>
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}
