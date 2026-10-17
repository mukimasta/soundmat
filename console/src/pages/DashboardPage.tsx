import { useConsole } from '../api/context';
import * as sel from '../api/selectors';

const LEVEL_COLOR = { info: '#5A554C', warning: 'var(--amber)', error: 'var(--red)' };

/** 看板。完整的状态指示和各组详细信息随系统监测加入；目前显示最近的警告和错误。 */
export function DashboardPage({ onBack }: { onBack: () => void }) {
  const s = useConsole();
  const items = s.connected ? sel.logs(s) : [];
  return (
    <>
      <header className="page-head">
        <button type="button" className="icon-btn" aria-label="返回垫面" onClick={onBack}>
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.9"
            strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 6l-6 6 6 6" /></svg>
        </button>
        <h1>看板</h1>
      </header>
      <div className="page-body">
        <section className="card" aria-label="最近的警告和错误">
          <h3>最近的警告和错误</h3>
          {items.length === 0 && <span className="hint" style={{ margin: 0 }}>没有记录。</span>}
          {items.map((it, i) => (
            <div key={i} className="log-item">
              <span className="when">{clock(it.at)}</span>
              <span className="sq" style={{ background: LEVEL_COLOR[it.level] }} />
              <span>{it.text}{it.count && it.count > 1 ? ` ×${it.count}` : ''}</span>
            </div>
          ))}
        </section>
      </div>
    </>
  );
}

function clock(at: number): string {
  const d = new Date(at * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}
