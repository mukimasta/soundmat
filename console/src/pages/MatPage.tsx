import { useClient, useConsole } from '../api/context';
import { getPath } from '../api/patch';
import { MatView } from '../components/MatView';

/** 垫面：控制台首页（按设计稿“垫面即首页”）。虚拟垫子模式下点按区域放下/拿起石头。 */
export function MatPage() {
  const s = useConsole();
  const client = useClient();
  const virtual = getPath<boolean>(s.state, 'status.current.virtual') === true;
  const canTap = s.connected && virtual;
  const mat = s.connected ? s.mat : null;
  const stones = mat?.occupied.length ?? 0;
  const hostLine = (getPath<string>(s.state, 'status.network.line')) ?? '';

  return (
    <>
      <header className="mat-header">
        <span className="brand">
          <span className="brand-name">
            <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true">
              <circle cx="12" cy="12" r="10" fill="none" stroke="#EDE8DF" strokeWidth="1.7" />
              <circle cx="12" cy="12" r="5.6" fill="none" stroke="#EDE8DF" strokeWidth="1.3" opacity="0.4" />
              <circle cx="15.6" cy="8.6" r="2.6" fill="#E5553A" />
            </svg>
            SoundMat
          </span>
          <span className="mono-sub">{hostLine || ' '}</span>
        </span>
        {canTap ? (
          <button type="button" className="btn-clear" onClick={() => client.clearVirtual()}>清空</button>
        ) : (
          <span className="header-right mono-sub">
            <span className="strong">{s.connected ? `${stones} 颗石头` : '—'}</span>
            <span>{s.connected ? fpsText(getPath<number>(s.state, 'status.mat.fps')) : '—'}</span>
          </span>
        )}
      </header>
      <div className="mat-wrap">
        <MatView
          geometry={s.geometry}
          pressure={mat?.pressure ?? null}
          occupied={mat?.occupied ?? []}
          ledCount={s.ledCount}
          leds={s.connected ? (s.streams.leds?.colors as ([number, number, number] | null)[] | undefined) : null}
          onZone={canTap ? (z) => void client.toggleZone(z) : undefined}
        />
        {!s.connected && <div className="mat-overlay">已断开 · 暂不显示垫面</div>}
      </div>
    </>
  );
}

function fpsText(fps: number | undefined): string {
  return typeof fps === 'number' ? `${fps.toFixed(1)} fps` : '— fps';
}
