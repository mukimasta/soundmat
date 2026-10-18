import { useState } from 'react';
import { useClient, useConsole } from '../api/context';
import * as sel from '../api/selectors';
import { ArrIcon } from '../components/ArrIcon';
import { Sheet } from '../components/Sheet';

/** 编排面板：点选即切换，新旧编排之间交叉淡化。 */
export function ArrangementSheet({ onClose }: { onClose: () => void }) {
  const s = useConsole();
  const client = useClient();
  const items = sel.arrangements(s);
  const curId = sel.currentId(s);
  const sw = sel.switching(s);
  const [error, setError] = useState<string | null>(null);

  const pick = async (id: string) => {
    if (id === curId && !sw) return;
    setError(null);
    try {
      await client.post(`/api/arrangements/${encodeURIComponent(id)}/play`);
    } catch (e) {
      setError(`无法切换：${(e as Error).message}`);
    }
  };

  return (
    <Sheet title="编排" onClose={onClose}>
      <p className="hint">点选即切换，新旧编排之间交叉淡化。</p>
      {items.map((a) => {
        const isCur = a.id === curId;
        const pct = sw ? `${Math.round(sw.progress * 100)}%` : '';
        const fading = !!sw && a.id === sw.from && a.id !== sw.to;
        let state = '点选切换到这个编排';
        if (sw && a.id === sw.to) state = `正在交叉淡化 ${pct}`;
        else if (isCur) state = '正在演奏';
        else if (fading) state = '正在淡出';
        return (
          <button key={a.id} type="button" className="arr-item" aria-pressed={isCur}
            disabled={!!a.error} onClick={() => void pick(a.id)}>
            <ArrIcon mode={a.mode} size={60} />
            <span className="np-text">
              <span className="arr-title">{a.title}</span>
              <span className="arr-mode">{a.modeLabel}</span>
              {a.description && <span className="arr-desc">{a.description}</span>}
              {a.error && <span className="arr-warn">无法加载：{a.error}</span>}
              {!a.error && a.missing.length > 0 && <span className="arr-warn">缺少 {a.missing.length} 个声音素材</span>}
              <span className="arr-state" style={{ color: isCur ? 'var(--text)' : 'var(--text-2)' }}>
                {isCur && !sw && <PlayingBars />}
                {state}
              </span>
            </span>
          </button>
        );
      })}
      {error && <p className="arr-warn" role="alert">{error}</p>}
    </Sheet>
  );
}

function PlayingBars() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
      <rect x="1" y="5" width="2.6" height="8" rx="1" fill="#EDE8DF" />
      <rect x="5.7" y="3" width="2.6" height="10" rx="1" fill="#EDE8DF" />
      <rect x="10.4" y="6" width="2.6" height="7" rx="1" fill="#EDE8DF" />
    </svg>
  );
}
