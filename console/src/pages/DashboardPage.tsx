import { useState } from 'react';
import { useClient, useConsole } from '../api/context';
import { getPath } from '../api/patch';
import * as sel from '../api/selectors';
import { Gauge, Segments, Spark, VuMeter } from '../components/Gauges';

const LEVEL_COLOR = { info: '#5A554C', warning: 'var(--amber)', error: 'var(--red)' };
const CHECK = '✓ ';
const CROSS = '✕ ';

interface Synth { online: boolean | null; synthdefsLoaded?: boolean; sampleRate?: number; avgLoad?: number; peakLoad?: number }

/** 看板：总体结论、三个状态指示和各组详细信息（设计稿）。 */
export function DashboardPage({ onBack }: { onBack: () => void }) {
  const s = useConsole();
  const st = s.state;
  const h = s.connected ? sel.health(s) : null;
  const g = <T,>(p: string) => getPath<T>(st, p);

  let verdict: { text: string; color: string; sq: string; dashed?: boolean; line?: string };
  if (!s.connected) {
    verdict = { text: '已断开', color: 'var(--text-2)', sq: 'transparent', dashed: true,
      line: '与装置的连接中断，正在重新连接。为了不让人误读，这里不显示过时的数据。' };
  } else if (!h) {
    verdict = { text: '正在检查', color: 'var(--text-2)', sq: 'transparent', dashed: true };
  } else if (h.overall === 'ok') {
    verdict = { text: '一切正常', color: 'var(--text)', sq: 'var(--green)' };
  } else {
    const L = sel.LOOK[h.overall];
    verdict = { text: L.text, color: L.tag, sq: L.sq, dashed: L.dashed,
      line: h.issues[0] ?? (h.overall === 'unknown' ? '部分状态暂时无法得知' : undefined) };
  }

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
        <section className="verdict" aria-label="总体状态">
          <span className="head" style={{ color: verdict.color }}>
            <Square color={verdict.sq} dashed={verdict.dashed} size={14} />{verdict.text}
          </span>
          {verdict.line && <span className="line" style={{ color: verdict.color === 'var(--text)' ? 'var(--text-2)' : verdict.color }}>{verdict.line}</span>}
          <span className="inds">
            {(['sound', 'mat', 'net'] as const).map((k) => {
              const level: sel.Level = h ? h[k].level : 'unknown';
              const L = sel.LOOK[level];
              return (
                <span key={k} className="ind">
                  <Square color={L.sq} dashed={L.dashed} size={9} />
                  <span className="lbl">{{ sound: '声音', mat: '垫子', net: '网络' }[k]}</span>
                  <span className="val" style={{ color: L.tag }}>{L.text}</span>
                </span>
              );
            })}
          </span>
        </section>
        {s.connected && (
          <>
            {SoundSection({ h })}
            {MatSection({ h })}
            {NetSection({ h })}
            {MachineSection()}
          </>
        )}
        <section className="card" aria-label="最近的警告和错误">
          <SecHead no="05" name="最近的警告和错误" />
          {(s.connected ? sel.logs(s) : []).length === 0 && <span className="small">没有记录。</span>}
          {(s.connected ? sel.logs(s) : []).map((it, i) => (
            <div key={i} className="log-item">
              <span className="when">{clock(it.at)}</span>
              <span className="sq" style={{ width: 8, height: 8, borderRadius: 2, background: LEVEL_COLOR[it.level] }} />
              <span>{it.text}{it.count && it.count > 1 ? ` ×${it.count}` : ''}</span>
            </div>
          ))}
        </section>
      </div>
    </>
  );

  function SoundSection({ h }: { h: sel.Health | null }) {
    const synth = g<Synth>('status.audio.synth');
    const lv = sel.levels(s);
    const layout = sel.setting<{ azimuths: number[]; names: string[] }>(s, 'sound.layout');
    const names = layout?.names ?? [];
    const out = lv?.output ?? [];
    const load = synth?.avgLoad ?? null;
    const engine = g<{ voices: number; budget: number }>('status.audio.engine');
    const xruns = g<number | null>('status.audio.xruns');
    const expectedRate = 48000;
    const rate = synth?.sampleRate;
    const rateOk = rate !== undefined && Math.abs(rate - expectedRate) < 1;
    const channels = g<number>('status.audio.channels');
    const buffer = g<{ period: number; periods: number; driver: string } | null>('status.audio.buffer');
    const missing = g<string[]>('status.audio.assets.missing') ?? [];
    const needed = g<number>('status.audio.assets.needed') ?? 0;
    const dev = g<{ name: string; usb: boolean } | null>('status.audio.outputDevice');
    const devBad = dev !== null && dev !== undefined && !dev.usb;
    const history = g<number[]>('status.audio.loadHistory') ?? [];
    return (
      <section className="card" aria-label="声音">
        <SecHead no="01" name="声音" ind={h?.sound.level} />
        <div style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: 8 }}>
          <div className="vu-col">
            <VuMeter levels={out.length ? out : (names.length ? names.map(() => -120) : [-120, -120])} names={names} />
            <span className="vu-vals">{(out.length ? out : [undefined, undefined]).map((l, i) => <span key={i}>{sel.dbText(l)}</span>)}</span>
            <span className="vu-vals" style={{ fontFamily: 'var(--font)', fontWeight: 400, color: 'var(--text-2)' }}>
              {(names.length ? names : ['左', '右']).map((n, i) => <span key={i}>{n}</span>)}
            </span>
          </div>
          <div className="load-col">
            <span className="small" style={{ fontSize: 12 }}>运算负载</span>
            <Gauge value={load} max={100} limit={85} text={load === null ? '—' : `${Math.round(load)}%`}
              label={load === null ? '合成器服务运算负载未知' : `合成器服务运算负载 ${Math.round(load)}%，红线是峰值上限 85%`} />
            <Spark values={history} max={100} />
            <span className="small">最近 1 分钟 · 红线是峰值上限 85%</span>
          </div>
        </div>
        <div className="grid2">
          <Tile label="卡顿" value={xruns ?? '—'} unit={xruns === null || xruns === undefined ? '' : '次'}
            sub={xruns === 0 ? `${CHECK}最近 1 小时没有卡顿` : xruns ? `${CROSS}最近 1 小时` : '无法读取'} tone={xruns ? 'warn' : xruns === 0 ? 'ok' : undefined} />
          <Tile label="在响声部" value={engine?.voices ?? '—'} unit={engine ? `/ ${engine.budget}` : ''}
            bar={engine ? engine.voices / engine.budget : undefined} />
          <Tile label="采样率" value={rate ? `${rate / 1000}` : '—'} unit="kHz"
            sub={rate ? (rateOk ? `${CHECK}与期望一致` : `${CROSS}期望 48 kHz`) : undefined} tone={rate ? (rateOk ? 'ok' : 'warn') : undefined} />
          <Tile label="声道" value={channels ?? '—'} unit="ch" sub={channels ? `${names.join(' · ')}` : undefined} />
          <Tile label="缓冲" value={buffer ? buffer.period : '—'} unit={buffer ? `${buffer.periods ? `× ${buffer.periods} · ` : ''}${buffer.driver}` : ''} />
          <Tile label="音色与素材" value={needed ? `${needed - missing.length} / ${needed}` : (synth?.synthdefsLoaded ? '全部' : '—')}
            unit={needed ? '' : '合成音色'}
            sub={missing.length ? `${CROSS}缺少 ${missing.length} 个` : synth?.synthdefsLoaded === false ? `${CROSS}音色没有加载` : `${CHECK}全部加载`}
            tone={missing.length || synth?.synthdefsLoaded === false ? 'warn' : 'ok'} />
        </div>
        {missing.length > 0 && (
          <div className="box"><span className="lbl">缺失的素材</span>
            {missing.map((m) => <span key={m} className="small" style={{ fontFamily: 'var(--mono)', overflowWrap: 'anywhere' }}>{m}</span>)}
          </div>
        )}
        <div className="box" style={devBad ? { background: 'var(--red-bg)' } : undefined}>
          <span className="lbl" style={devBad ? { color: 'var(--red-line)' } : undefined}>合成器服务实际使用的输出设备</span>
          <span className="val" style={devBad ? { color: 'var(--red-line)' } : undefined}>{dev ? (dev.usb ? `USB 声卡 · ${dev.name.split(' - ').pop()}` : dev.name) : '未知'}</span>
          {devBad && <span className="note" style={{ color: 'var(--red-line)' }}>期望 USB 声卡，音箱不会发声</span>}
        </div>
        <ToneButtons names={names} />
      </section>
    );
  }

  function MatSection({ h }: { h: sel.Health | null }) {
    const m = g<{ source: string; connected: boolean | null; port: string | null; fps: number | null; checksumErrors: number | null }>('status.mat');
    const virtual = m?.source === 'virtual';
    const hist = g<number[]>('status.matHistory') ?? [];
    return (
      <section className="card" aria-label="垫子">
        <SecHead no="02" name="垫子" ind={h?.mat.level} />
        <span className="small" style={{ fontSize: 12 }}>传感帧率</span>
        <span><span className="big-num">{virtual || m?.fps == null ? '—' : m.fps.toFixed(1)}</span>
          <span className="small" style={{ marginLeft: 6 }}>{virtual ? '虚拟垫子没有传感帧率' : 'fps'}</span></span>
        {!virtual && <><Spark values={hist} max={80} height={38} /><span className="small">最近 60 秒 · 也是灯光的实际刷新率</span></>}
        <div>
          <KV k="输入" v={virtual ? '虚拟垫子' : '压力垫控制器'} />
          <KV k="控制器" v={virtual ? '未使用' : m?.connected ? `已连接 · ${m.port ?? ''}` : '未连接'} />
          <KV k="校验错误" v={virtual || m?.checksumErrors == null ? '—' : String(m.checksumErrors)} />
        </div>
      </section>
    );
  }

  function NetSection({ h }: { h: sel.Health | null }) {
    const n = g<{ name: string | null; address: string | null; tailscale: string | null; tailscaleAddress: string | null }>('status.network');
    const host = g<string>('status.machine.host');
    return (
      <section className="card" aria-label="网络">
        <SecHead no="03" name="网络" ind={h?.net.level} />
        <span style={{ fontSize: 16, fontWeight: 600 }}>{n?.name ?? (n?.address ? '已联网' : '未连接网络')}</span>
        <div>
          <KV k="地址" v={[host ? `${host}.local` : null, n?.address].filter(Boolean).join(' · ') || '—'} />
          <KV k="Tailscale" v={n?.tailscale ? `${n.tailscale === 'Running' ? '已连接' : n.tailscale}${n.tailscaleAddress ? ` · ${n.tailscaleAddress}` : ''}` : '未知'} />
        </div>
      </section>
    );
  }

  function MachineSection() {
    const m = g<{ host: string; model: string | null; tempC: number | null; throttled: boolean | null; memUsedMB: number | null;
      memTotalMB: number | null; diskFreeGB: number | null; diskTotalGB: number | null; uptime: number | null; programUptime: number }>('status.machine');
    if (!m) return null;
    const memFrac = m.memUsedMB != null && m.memTotalMB ? m.memUsedMB / m.memTotalMB : null;
    const diskFrac = m.diskFreeGB != null && m.diskTotalGB ? 1 - m.diskFreeGB / m.diskTotalGB : null;
    const hot = (m.tempC ?? 0) >= 80 || m.throttled;
    return (
      <section className="card" aria-label="机器">
        <SecHead no="04" name="机器" ind={hot ? 'warn' : 'ok'} />
        <div style={{ display: 'grid', gridTemplateColumns: '124px minmax(0, 1fr)', gap: 12, alignItems: 'center' }}>
          <Gauge value={m.tempC} max={100} limit={80} width={124} text={m.tempC == null ? '—' : `${Math.round(m.tempC)}°`}
            label={m.tempC == null ? '温度未知' : `温度 ${m.tempC} 摄氏度，红线是 80 度`} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div><KV k="内存" v={m.memUsedMB != null ? `${(m.memUsedMB / 1024).toFixed(1)} / ${((m.memTotalMB ?? 0) / 1024).toFixed(1)} GB` : '—'} /><Segments frac={memFrac} /></div>
            <div><KV k="存储空间" v={m.diskFreeGB != null ? `${Math.round(m.diskFreeGB)} GB 可用` : '—'} /><Segments frac={diskFrac} warn={0.9} /></div>
          </div>
        </div>
        <div>
          <KV k="机器" v={m.model ?? m.host} />
          <KV k="降频" v={m.throttled == null ? '—' : m.throttled ? '有' : '无'} />
          <KV k="已运行" v={m.uptime != null ? duration(m.uptime) : duration(m.programUptime)} />
        </div>
      </section>
    );
  }
}

function ToneButtons({ names }: { names: string[] }) {
  const client = useClient();
  const [on, setOn] = useState<number | null>(null);
  const labels = names.length ? names : ['左', '右'];
  const press = async (i: number) => {
    setOn(i);
    try {
      await client.post('/api/audio/test-tone', { channel: i });
    } finally {
      setTimeout(() => setOn((x) => (x === i ? null : x)), 1100);
    }
  };
  return (
    <div className="tone-row">
      <span>声道测试</span>
      <span className="btns">
        {labels.map((n, i) => (
          <button key={i} type="button" aria-pressed={on === i} aria-label={`${n}声道测试音`} onClick={() => void press(i)}>
            {on === i ? `${n} · 发声` : n}
          </button>
        ))}
      </span>
    </div>
  );
}

function Square({ color, dashed, size }: { color: string; dashed?: boolean; size: number }) {
  return <span className="sq" style={{ width: size, height: size, background: dashed ? 'transparent' : color,
    border: dashed ? `2px dashed #6E685E` : `2px solid ${color}` }} />;
}

function SecHead({ no, name, ind }: { no: string; name: string; ind?: sel.Level }) {
  const L = ind ? sel.LOOK[ind] : null;
  return (
    <div className="sec-head">
      <span className="t"><span className="no">{no}</span><span className="nm">{name}</span></span>
      {L && <span className="st" style={{ color: L.tag }}>{L.text}</span>}
    </div>
  );
}

function Tile({ label, value, unit, sub, tone, bar }: {
  label: string; value: string | number; unit?: string; sub?: string; tone?: 'ok' | 'warn'; bar?: number;
}) {
  const warn = tone === 'warn';
  return (
    <div className="tile" style={warn ? { background: 'var(--amber-bg)' } : undefined}>
      <span className="lbl">{label}</span>
      <span><span className="num" style={warn ? { color: 'var(--amber-line)' } : undefined}>{value}</span>{unit && <span className="unit">{unit}</span>}</span>
      {bar !== undefined && <span className="bar"><span style={{ width: `${Math.round(Math.min(1, bar) * 100)}%` }} /></span>}
      {sub && <span className="sub" style={{ color: warn ? 'var(--amber-line)' : tone === 'ok' ? 'var(--green-t)' : 'var(--text-2)' }}>{sub}</span>}
    </div>
  );
}

function KV({ k, v }: { k: string; v: string }) {
  return <div className="kv"><span>{k}</span><span>{v}</span></div>;
}

function clock(at: number): string {
  const d = new Date(at * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

function duration(sec: number): string {
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h ? `${h} 小时 ${m} 分` : `${m} 分`;
}
