import { useConsole } from './api/context';
import { getPath } from './api/patch';
import { DisconnectedBanner, VirtualBanner } from './components/Banners';
import { MatPage } from './pages/MatPage';

export function App() {
  const s = useConsole();
  const virtual = getPath<boolean>(s.state, 'status.current.virtual') === true;
  return (
    <div className="app">
      {s.connected && virtual && <VirtualBanner hint="点按垫面放下，再点拿起" />}
      {!s.connected && <DisconnectedBanner />}
      <MatPage />
    </div>
  );
}
