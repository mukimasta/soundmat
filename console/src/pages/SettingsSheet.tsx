import { useState } from 'react';
import { useClient, useConsole } from '../api/context';
import * as sel from '../api/selectors';
import { Sheet } from '../components/Sheet';

const PRESETS: Record<string, { label: string; count: number }> = {
  stereo: { label: '2 只 · 立体声', count: 2 },
  quad: { label: '4 只 · 四声道', count: 4 },
  octo: { label: '8 只 · 八声道', count: 8 },
};

interface Layout {
  azimuths: number[];
  names: string[];
}

function presetOf(layout: Layout | undefined): string {
  const n = layout?.azimuths.length ?? 2;
  return n === 4 ? 'quad' : n === 8 ? 'octo' : 'stereo';
}

/** 设置：修改立即生效并自动保存；配置只读显示。 */
export function SettingsSheet({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const s = useConsole();
  const client = useClient();
  const [error, setError] = useState<string | null>(null);
  const layout = sel.setting<Layout>(s, 'sound.layout');
  const orientation = sel.setting<number>(s, 'sound.orientation') ?? 0;
  const def = sel.setting<string>(s, 'run.defaultArrangement') ?? '';
  const stems = sel.setting<boolean>(s, 'recording.stems') ?? true;

  const save = async (changes: Record<string, unknown>) => {
    setError(null);
    try {
      await client.post('/api/settings', { changes });
    } catch (e) {
      setError(`没有保存：${(e as Error).message}`);
    }
  };

  return (
    <Sheet title="设置" onClose={onClose} onBack={onBack}>
      <p className="hint">修改立即生效，并自动保存。</p>
      <section className="card">
        <h3>声音</h3>
        <div className="row">
          <label htmlFor="layout">音箱布局</label>
          <select id="layout" value={presetOf(layout)} onChange={(e) => void save({ 'sound.layout': e.target.value })}>
            {Object.entries(PRESETS).map(([k, p]) => <option key={k} value={k}>{p.label}</option>)}
          </select>
        </div>
        <LayoutDiagram layout={layout} orientation={orientation} />
        <div className="row">
          <span>垫面朝向偏移<span className="sub">垫面 12 点方向对着房间的哪一边</span></span>
          <span className="stepper">
            <button type="button" aria-label="逆时针 15 度" onClick={() => void save({ 'sound.orientation': orientation - 15 })}>−</button>
            <span>{Math.round(orientation)}°</span>
            <button type="button" aria-label="顺时针 15 度" onClick={() => void save({ 'sound.orientation': orientation + 15 })}>+</button>
          </span>
        </div>
      </section>
      <section className="card">
        <h3>运行与录制</h3>
        <div className="row">
          <label htmlFor="def">开机后的默认编排</label>
          <select id="def" value={def} onChange={(e) => void save({ 'run.defaultArrangement': e.target.value })}>
            {sel.arrangements(s).map((a) => <option key={a.id} value={a.id}>{a.title}</option>)}
          </select>
        </div>
        <div className="row"><span>声音素材库位置</span><span className="val">{sel.setting<string>(s, 'run.soundLibrary')}</span></div>
        <div className="row"><span>录制保存位置</span><span className="val">{sel.setting<string>(s, 'recording.path')}</span></div>
        <div className="row">
          <span>录制分轨<span className="sub">每个环一轨，另加混响等回送</span></span>
          <button type="button" role="switch" aria-checked={stems} aria-label="录制分轨" className="toggle"
            onClick={() => void save({ 'recording.stems': !stems })} />
        </div>
      </section>
      <section className="card">
        <h3>配置 · 只读</h3>
        <p className="hint" style={{ margin: 0 }}>来自仓库里的配置文件，部署时确定。</p>
        {s.config.map((r) => <div key={r.label} className="ro-row"><span>{r.label}</span><span>{r.value}</span></div>)}
      </section>
      {error && <p className="arr-warn" role="alert">{error}</p>}
    </Sheet>
  );
}

/** 音箱与垫面朝向示意：垫面画在中间，小点是它的 12 点方向。 */
function LayoutDiagram({ layout, orientation }: { layout?: Layout; orientation: number }) {
  const az = layout?.azimuths ?? [270, 90];
  const names = layout?.names ?? [];
  const pt = (deg: number, r: number) => {
    const a = (deg * Math.PI) / 180;
    return [130 + r * 1.9 * Math.sin(a), 64 - r * Math.cos(a) * 0.82];
  };
  return (
    <svg width="100%" viewBox="0 0 260 128" role="img"
      aria-label={`音箱布局示意：${az.length} 只音箱，垫面朝向偏移 ${Math.round(orientation)} 度`}>
      <circle cx="130" cy="64" r="34" fill="none" stroke="#5A554C" strokeWidth="1.2" />
      <circle cx="130" cy="64" r="20" fill="none" stroke="#3A3732" strokeWidth="1" />
      <g transform={`rotate(${orientation} 130 64)`}>
        <circle cx="130" cy="26" r="3.4" fill="#E5553A" />
        <path d="M130 32 L130 48" stroke="#EDE8DF" strokeWidth="1.4" strokeLinecap="round" />
      </g>
      {az.map((a, i) => {
        const [x, y] = pt(a, 56);
        return (
          <g key={i}>
            <rect x={x - 11} y={y - 10} width="22" height="20" rx="5" fill="#2A2824" stroke="#5A554C" />
            <circle cx={x} cy={y} r="4.5" fill="none" stroke="#EDE8DF" strokeWidth="1.2" />
            <text x={x} y={y + 22} fontSize="10" fill="#A49D91" textAnchor="middle">{names[i] ?? i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
}
