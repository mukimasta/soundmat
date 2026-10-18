import { useState } from 'react';
import { useClient } from './api/context';
import { useConsole } from './api/context';
import * as sel from './api/selectors';
import { BottomNav } from './components/BottomNav';
import { DisconnectedBanner, VirtualBanner } from './components/Banners';
import { ArrangementSheet } from './pages/ArrangementSheet';
import { DashboardPage } from './pages/DashboardPage';
import { MatPage } from './pages/MatPage';
import { MenuSheet } from './pages/MenuSheet';
import { RecordingsSheet } from './pages/RecordingsSheet';
import { SettingsSheet } from './pages/SettingsSheet';
import { UpdateSheet } from './pages/UpdateSheet';
import { RestartSheet } from './pages/RestartSheet';

type Page = 'mat' | 'dash';
type SheetKind = 'none' | 'arr' | 'menu' | 'set' | 'recs' | 'upd' | 'restart';

export function App() {
  const s = useConsole();
  const client = useClient();
  const [toast, setToast] = useState<string | null>(null);
  const [page, setPage] = useState<Page>('mat');
  const [sheet, setSheet] = useState<SheetKind>('none');
  const virtual = sel.isVirtual(s);
  const close = () => setSheet('none');
  const alert = s.connected ? sel.alertOf(sel.health(s)) : null;
  const rec = s.connected ? sel.recording(s) : { state: 'idle' as const };
  const counting = rec.state === 'countdown';
  const flashing = rec.state === 'recording' && !!rec.flash;
  const recording = rec.state === 'recording';
  const startStop = async () => {
    setToast(null);
    try {
      await client.post(recording ? '/api/recording/stop' : '/api/recording/start');
    } catch (e) {
      setToast(recording ? '无法停止录制' : `无法开始录制：${(e as Error).message}`);
      setTimeout(() => setToast(null), 5000);
    }
  };
  const record = {
    label: counting ? `倒计时 ${rec.count ?? ''}` : flashing ? '打板' : recording ? sel.clockText(rec.elapsed ?? 0) : '录制',
    aria: counting ? '正在倒计时' : recording ? '停止录制' : '开始录制',
    disabled: !s.connected || counting,
    onPress: () => void startStop(),
    inner: (counting ? rec.count ?? 3 : recording ? 'stop' : 'idle') as 'idle' | 'stop' | number,
  };
  const segments = counting
    ? [0, 1, 2].map((i) => ({ d: arcPath(i), color: i < (rec.count ?? 3) ? '#FFF6E6' : '#2E2C27' }))
    : recording ? [0, 1, 2].map((i) => ({ d: arcPath(i), color: 'var(--red)' })) : [];
  const overlay = counting ? <div className="count-overlay" aria-live="assertive">{rec.count}</div>
    : flashing ? <div className="slate-overlay">打板</div> : null;

  return (
    <div className="app">
      {s.connected && virtual && (
        <VirtualBanner hint={page === 'mat' ? '点按垫面放下，再点拿起' : '输入来自点击，不是实体垫子'} />
      )}
      {!s.connected && <DisconnectedBanner />}
      {page === 'mat' && alert && (
        <div className="alert" style={{ background: alert.level === 'error' ? 'var(--red-bg)' : 'var(--amber-bg)',
          color: alert.level === 'error' ? 'var(--red-line)' : 'var(--amber-line)' }}>
          <button type="button" className="alert-main" onClick={() => setPage('dash')}>
            <span style={{ flex: 'none', width: 10, height: 10, borderRadius: 3, background: sel.LOOK[alert.level].sq }} />
            <span className="txt">{alert.text}</span>
            <span className="go">看板
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"
                strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 6l6 6-6 6" /></svg>
            </span>
          </button>
          {/* 声音出问题时就近给出重启入口（打开重启面板，仍要再确认一次） */}
          {alert.text.startsWith('声音') && (
            <button type="button" className="alert-act" onClick={() => setSheet('restart')}>重启</button>
          )}
        </div>
      )}
      {page === 'mat' ? (
        <>
          <MatPage onOpenArrangements={() => setSheet('arr')} overlay={overlay} />
          {toast && <div className="toast" role="alert">{toast}</div>}
          <BottomNav
            onDash={() => setPage('dash')}
            onMenu={() => setSheet('menu')}
            dot={alert ? sel.LOOK[alert.level].sq : null}
            dashLabel={alert ? '看板，有 1 项需要处理' : '看板'}
            record={record}
            segments={segments}
          />
        </>
      ) : (
        <DashboardPage onBack={() => setPage('mat')} />
      )}
      {sheet === 'arr' && <ArrangementSheet onClose={close} />}
      {sheet === 'menu' && (
        <MenuSheet onClose={close} onOpen={(k) => setSheet(k)}
          recordingsText={sel.recordings(s).length ? `${sel.recordings(s).length} 段` : '还没有'} />
      )}
      {sheet === 'recs' && <RecordingsSheet onClose={close} onBack={() => setSheet('menu')} />}
      {sheet === 'set' && <SettingsSheet onClose={close} onBack={() => setSheet('menu')} />}
      {sheet === 'upd' && <UpdateSheet onClose={close} onBack={() => setSheet('menu')} />}
      {sheet === 'restart' && <RestartSheet onClose={close} onBack={() => setSheet('menu')} />}
    </div>
  );
}

/** 录制按钮外圈的三段弧（倒计时每秒熄灭一段） */
function arcPath(i: number): string {
  const a0 = ((i * 120 + 6 - 90) * Math.PI) / 180;
  const a1 = (((i + 1) * 120 - 6 - 90) * Math.PI) / 180;
  const r = 45;
  return `M${(r * Math.cos(a0)).toFixed(2)} ${(r * Math.sin(a0)).toFixed(2)} A${r} ${r} 0 0 1 ${(r * Math.cos(a1)).toFixed(2)} ${(r * Math.sin(a1)).toFixed(2)}`;
}
