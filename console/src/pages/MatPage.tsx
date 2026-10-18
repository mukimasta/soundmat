import { useClient, useConsole } from '../api/context';
import { getPath } from '../api/patch';
import * as sel from '../api/selectors';
import { ArrIcon } from '../components/ArrIcon';
import { MatView } from '../components/MatView';
import { LayerMeters } from '../components/LayerMeters';
import { Volume } from '../components/Volume';

/** 垫面：控制台首页（设计稿“垫面即首页”）。虚拟垫子模式下点按区域放下/拿起石头。 */
export function MatPage({ onOpenArrangements, overlay }: { onOpenArrangements: () => void; overlay?: React.ReactNode }) {
  const s = useConsole();
  const client = useClient();
  const virtual = sel.isVirtual(s);
  const canTap = s.connected && virtual;
  const mat = s.connected ? s.mat : null;
  const stones = mat?.occupied.length ?? 0;
  const hostLine = getPath<string>(s.state, 'status.network.line') ?? '';
  const cur = sel.current(s);
  const st = sel.modeStatus(s);
  const sw = sel.switching(s);
  const lv = s.connected ? sel.levels(s) : null;
  const target = sw ? sel.arrangements(s).find((a) => a.id === sw.to) : null;

  let left = '';
  let right = '';
  if (!s.connected) {
    left = '已断开 · 不显示过时的数据';
  } else if (st) {
    left = st.text;
    const out = lv?.output?.length ? Math.max(...lv.output) : undefined;
    right = st.reading ?? `输出 ${sel.dbText(out)} dB`;
  }
  const line = sw && target
    ? `正在切换到 ${target.title} · ${Math.round(sw.progress * 100)}%`
    : cur ? `${cur.modeLabel} · ${sel.transportWord(st)}` : '';

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
          leds={s.connected ? ((s.streams.leds?.colors as string | undefined) ?? null) : null}
          onZone={canTap ? (z) => void client.toggleZone(z) : undefined}
        />
        {!s.connected && <div className="mat-overlay">已断开 · 暂不显示垫面</div>}
        {overlay}
      </div>
      <div className="sec-line">
        <span className="left">{left}</span>
        <span className="right">{right}</span>
      </div>
      <LayerMeters meters={s.connected ? sel.meters(s) : []} levels={lv} />
      {s.connected && <div className="mat-volume"><Volume /></div>}
      <div className="spacer" />
      {cur && (
        <div className="now-playing">
          <button type="button" onClick={onOpenArrangements} aria-label={`当前编排：${cur.title}，打开编排列表`}>
            <ArrIcon mode={cur.mode} />
            <span className="np-text">
              <span className="np-title">{cur.title}</span>
              <span className="np-line">{line}</span>
              {sw && <span className="progress"><span style={{ width: `${Math.round(sw.progress * 100)}%` }} /></span>}
            </span>
            <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#A49D91" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M6.5 14.5L12 9l5.5 5.5" />
            </svg>
          </button>
        </div>
      )}
    </>
  );
}

function fpsText(fps: number | undefined): string {
  return typeof fps === 'number' ? `${fps.toFixed(1)} fps` : '— fps';
}
