import { useState } from 'react';
import { useConsole } from './api/context';
import * as sel from './api/selectors';
import { BottomNav } from './components/BottomNav';
import { DisconnectedBanner, VirtualBanner } from './components/Banners';
import { ArrangementSheet } from './pages/ArrangementSheet';
import { DashboardPage } from './pages/DashboardPage';
import { MatPage } from './pages/MatPage';
import { MenuSheet } from './pages/MenuSheet';
import { SettingsSheet } from './pages/SettingsSheet';

type Page = 'mat' | 'dash';
type SheetKind = 'none' | 'arr' | 'menu' | 'set';

export function App() {
  const s = useConsole();
  const [page, setPage] = useState<Page>('mat');
  const [sheet, setSheet] = useState<SheetKind>('none');
  const virtual = sel.isVirtual(s);
  const close = () => setSheet('none');
  const alert = s.connected ? sel.alertOf(sel.health(s)) : null;

  return (
    <div className="app">
      {s.connected && virtual && (
        <VirtualBanner hint={page === 'mat' ? '点按垫面放下，再点拿起' : '输入来自点击，不是实体垫子'} />
      )}
      {!s.connected && <DisconnectedBanner />}
      {page === 'mat' && alert && (
        <button type="button" className="alert" onClick={() => setPage('dash')}
          style={{ background: alert.level === 'error' ? 'var(--red-bg)' : 'var(--amber-bg)',
            color: alert.level === 'error' ? 'var(--red-line)' : 'var(--amber-line)' }}>
          <span style={{ flex: 'none', width: 10, height: 10, borderRadius: 3, background: sel.LOOK[alert.level].sq }} />
          <span className="txt">{alert.text}</span>
          <span className="go">看板
            <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2"
              strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 6l6 6-6 6" /></svg>
          </span>
        </button>
      )}
      {page === 'mat' ? (
        <>
          <MatPage onOpenArrangements={() => setSheet('arr')} />
          <BottomNav
            onDash={() => setPage('dash')}
            onMenu={() => setSheet('menu')}
            dot={alert ? sel.LOOK[alert.level].sq : null}
            dashLabel={alert ? '看板，有 1 项需要处理' : '看板'}
            record={{ label: '录制', aria: '录制（尚未实现）', disabled: true, onPress: () => {}, inner: 'idle' }}
          />
        </>
      ) : (
        <DashboardPage onBack={() => setPage('mat')} />
      )}
      {sheet === 'arr' && <ArrangementSheet onClose={close} />}
      {sheet === 'menu' && <MenuSheet onClose={close} onOpen={(k) => k === 'set' && setSheet('set')} />}
      {sheet === 'set' && <SettingsSheet onClose={close} onBack={() => setSheet('menu')} />}
    </div>
  );
}
