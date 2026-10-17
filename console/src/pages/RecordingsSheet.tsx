import { useConsole } from '../api/context';
import * as sel from '../api/selectors';
import { Sheet } from '../components/Sheet';

/** 已录制：每项显示时间、编排、时长，可以下载（整个文件夹打包成 zip）。 */
export function RecordingsSheet({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const s = useConsole();
  const items = sel.recordings(s);
  return (
    <Sheet title="已录制" onClose={onClose} onBack={onBack}>
      <p className="hint">每次录制保存总输出、各环分轨和会话数据，以开始时间和编排命名。</p>
      {items.length === 0 && (
        <p className="hint">还没有录制。按底部的录制按钮开始，录下的内容会出现在这里，可以直接下载。</p>
      )}
      {items.map((it) => (
        <div key={it.name} className="rec-item">
          <span className="np-text">
            <span className="arr-title" style={{ fontSize: 15 }}>{when(it.startedAt)}</span>
            <span className="arr-mode">{it.title || '—'} · {it.duration != null ? sel.clockText(it.duration) : '—'}
              {!it.audio && ' · 只有会话数据'}</span>
          </span>
          <a className="icon-btn" href={`/api/recordings/${encodeURIComponent(it.name)}/download`}
            download aria-label="下载这段录制">
            <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
              strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M12 4v11 M7 10l5 5 5-5 M5 19h14" /></svg>
          </a>
        </div>
      ))}
    </Sheet>
  );
}

function when(iso: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}`;
}
