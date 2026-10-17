import { useEffect, useState } from 'react';
import { useClient, useConsole } from '../api/context';
import { getPath } from '../api/patch';
import { Sheet } from '../components/Sheet';

interface Release { tag: string; commit: string; branch: string | null; builtAt: string | null; current: boolean }
interface Info { allowed: boolean; enabled: boolean; available: Release[]; error: string | null }
interface Version { commit: string; branch: string | null; deployedAt: string | null; dirty: boolean | null; source: string }
interface UpdateStatus { enabled: boolean; state: string; message: string; previous: string | null; failed: string | null }

const MAIN = ['master', 'main'];

/**
 * 软件更新（CONSOLE「软件更新」）：当前版本、GitHub 上可以安装的版本、更新与回到上一版。
 * 只有从本机或 Tailscale 打开、并且装置是从发布包运行时才有更新按钮；更新需要再点一次确认。
 */
export function UpdateSheet({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const s = useConsole();
  const client = useClient();
  const version = getPath<Version | null>(s.state, 'status.program.version');
  const status = getPath<UpdateStatus>(s.state, 'status.update');
  const [info, setInfo] = useState<Info | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [allBranches, setAllBranches] = useState(false);
  const [armed, setArmed] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    client.get('/api/update')
      .then((r) => { if (live) setInfo(r as Info); })
      .catch((e) => { if (live) setLoadError(String(e.message ?? e)); });
    return () => { live = false; };
  }, [client]);

  const busy = status && !['idle', 'error'].includes(status.state);
  const releases = (info?.available ?? []).filter((r) => allBranches || !r.branch || MAIN.includes(r.branch));
  const others = (info?.available ?? []).length - releases.length;

  const act = async (fn: () => Promise<unknown>) => {
    setActionError(null);
    try { await fn(); } catch (e) { setActionError(String((e as Error).message ?? e)); }
    setArmed(null);
  };

  return (
    <Sheet title="软件更新" onClose={onClose} onBack={onBack}>
      <div className="upd-current" aria-label="当前版本">
        <span className="lbl">当前版本</span>
        <span className="val">{version ? version.commit : '未知'}{version?.dirty ? ' · 有未提交的改动' : ''}</span>
        <span className="small">{[version?.branch, version?.deployedAt ? when(version.deployedAt) : null,
          version?.source === 'git' ? '开发机' : null].filter(Boolean).join(' · ') || ' '}</span>
      </div>

      {status?.failed && <p className="hint warn">版本 {status.failed} 启动失败，已自动回到当前版本。</p>}
      {busy && <p className="hint" role="status">{status!.message || '正在更新…'}</p>}
      {status?.state === 'error' && <p className="hint warn" role="alert">{status.message}</p>}
      {actionError && <p className="hint warn" role="alert">{actionError}</p>}

      {info && !info.enabled && <p className="hint">这里不是从发布包运行的（例如开发机），不能更新。</p>}
      {info && info.enabled && !info.allowed && (
        <p className="hint">只有从本机或 Tailscale 打开的控制台能更新，避免现场误点让装置停下。</p>
      )}
      {loadError && <p className="hint warn">{loadError}</p>}
      {info?.error && <p className="hint warn">{info.error}</p>}

      {info?.allowed && (
        <>
          <p className="hint">更新时装置会重新启动，演奏中断十几秒。新版本起不来时会自动回到当前版本。</p>
          {releases.map((r) => (
            <div key={r.tag} className="rec-item" data-release={r.tag}>
              <span className="np-text">
                <span className="arr-title" style={{ fontSize: 15, fontFamily: 'var(--mono)' }}>{r.commit}</span>
                <span className="arr-mode">{[r.branch, r.builtAt ? when(r.builtAt) : null].filter(Boolean).join(' · ')}</span>
              </span>
              {r.current ? <span className="mono-sub">正在运行</span> : (
                <button type="button" className="btn-clear" disabled={!!busy}
                  onClick={() => (armed === r.tag
                    ? act(() => client.post('/api/update', { tag: r.tag }))
                    : setArmed(r.tag))}>
                  {armed === r.tag ? '确认更新' : '更新'}
                </button>
              )}
            </div>
          ))}
          {releases.length === 0 && !info.error && <p className="hint">GitHub 上还没有发布包。在开发机上运行 scripts/release.py 发布。</p>}
          {others > 0 && (
            <button type="button" className="link-btn" onClick={() => setAllBranches((v) => !v)}>
              {allBranches ? '只看主分支' : `显示其他分支（${others}）`}
            </button>
          )}
          {status?.previous && (
            <button type="button" className="link-btn" disabled={!!busy}
              onClick={() => (armed === 'rollback' ? act(() => client.post('/api/update/rollback')) : setArmed('rollback'))}>
              {armed === 'rollback' ? `确认回到上一版 ${status.previous}` : `回到上一版 ${status.previous}`}
            </button>
          )}
        </>
      )}
    </Sheet>
  );
}

function when(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}月${d.getDate()}日 ${p(d.getHours())}:${p(d.getMinutes())}`;
}
