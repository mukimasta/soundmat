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

  return (
    <div className="app">
      {s.connected && virtual && (
        <VirtualBanner hint={page === 'mat' ? '点按垫面放下，再点拿起' : '输入来自点击，不是实体垫子'} />
      )}
      {!s.connected && <DisconnectedBanner />}
      {page === 'mat' ? (
        <>
          <MatPage onOpenArrangements={() => setSheet('arr')} />
          <BottomNav
            onDash={() => setPage('dash')}
            onMenu={() => setSheet('menu')}
            dot={null}
            dashLabel="看板"
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
