import { useEffect, useState } from 'react';
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
            <RhythmSection />
            {NetSection({ h })}
            {MachineSection()}
          </>
        )}
        <section className="card" aria-label="最近的警告和错误">
          <SecHead no="06" name="最近的警告和错误" />
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
    // 运算负载：合成器（scsynth 自报）和主机程序（占单核）里更高的那个，也就是先撑不住的一方
    const synthLoad = synth?.avgLoad ?? null;
    const progLoad = g<number | null>('status.machine.programCpu') ?? null;
    const progHistory = g<number[]>('status.machine.programCpuHistory') ?? [];
    const bottleneck: 'synth' | 'program' | null = synthLoad === null && progLoad === null ? null
      : (progLoad ?? -1) > (synthLoad ?? -1) ? 'program' : 'synth';
    const load = bottleneck === 'program' ? progLoad : synthLoad;
    const engine = g<{ voices: number; budget: number }>('status.engine');
    const xruns = g<number | null>('status.audio.xruns');
    const expectedRate = 48000;
    const rate = synth?.sampleRate;
    const rateOk = rate !== undefined && Math.abs(rate - expectedRate) < 1;
    const channels = g<number>('status.audio.channels');
    const buffer = g<{ period: number; periods: number; driver: string } | null>('status.audio.buffer');
    const missing = g<string[]>('status.assets.missing') ?? [];
    const needed = g<number>('status.assets.needed') ?? 0;
    const dev = g<{ name: string; usb: boolean } | null>('status.audio.outputDevice');
    const devBad = dev !== null && dev !== undefined && !dev.usb;
    const synthHistory = g<number[]>('status.audio.loadHistory') ?? [];
    const history = maxTail(synthHistory, progHistory);
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
            <span className="small" style={{ fontSize: 12 }}>
              运算负载{bottleneck ? ` · ${bottleneck === 'program' ? '主机程序' : '合成器'}` : ''}
            </span>
            <Gauge value={load === null ? null : Math.min(load, 100)} max={100} limit={85} text={load === null ? '—' : `${Math.round(load)}%`}
              label={load === null ? '运算负载未知'
                : `运算负载 ${Math.round(load)}%，来自${bottleneck === 'program' ? '主机程序' : '合成器'}，红线是上限 85%`} />
            <Spark values={history} max={100} />
            <span className="small" data-load="both">
              合成器 {synthLoad === null ? '—' : `${Math.round(synthLoad)}%`} · 主机程序 {progLoad === null ? '—' : `${Math.round(progLoad)}%`}（单核）
            </span>
            <span className="small">最近 1 分钟取两者中较高的 · 红线是上限 85%</span>
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
        {!virtual && <><Spark values={hist} max={80} height={38} /><span className="small">最近 60 秒</span></>}
        <div>
          <KV k="输入" v={virtual ? '虚拟垫子' : '压力垫控制器'} />
          <KV k="控制器" v={virtual ? '未使用' : m?.connected ? `已连接 · ${m.port ?? ''}` : '未连接'} />
          <KV k="校验错误" v={virtual || m?.checksumErrors == null ? '—' : String(m.checksumErrors)} />
        </div>
      </section>
    );
  }

  function NetSection({ h }: { h: sel.Health | null }) {
    const n = g<{ name: string | null; address: string | null; tailscale: string | null; tailscaleAddress: string | null;
      localName: string | null; kind: NetKind | null; apClients: number | null }>('status.network');
    const kind = n?.kind ? NET_KIND[n.kind] : null;
    return (
      <section className="card" aria-label="网络">
        <SecHead no="04" name="网络" ind={h?.net.level} />
        <span style={{ fontSize: 16, fontWeight: 600 }}>{kind ?? (n?.address ? '已联网' : '未连接网络')}</span>
        <div>
          {n?.name && <KV k="连接" v={n.name} />}
          {n?.kind === 'selfHotspot' && <KV k="连着的设备" v={n.apClients == null ? '未知' : `约 ${n.apClients} 台`} />}
          <KV k="地址" v={[n?.localName, n?.address].filter(Boolean).join(' · ') || '—'} />
          <KV k="Tailscale" v={n?.tailscale ? `${n.tailscale === 'Running' ? '已连接' : n.tailscale}${n.tailscaleAddress ? ` · ${n.tailscaleAddress}` : ''}` : '未知'} />
        </div>
      </section>
    );
  }

  function MachineSection() {
    const m = g<{ host: string; model: string | null; tempC: number | null; throttled: boolean | null; memUsedMB: number | null;
      memTotalMB: number | null; diskFreeGB: number | null; diskTotalGB: number | null; uptime: number | null; programUptime: number;
      programCpu?: number | null; cpu?: number | null; cores?: number | null; programCpuHistory?: number[] }>('status.machine');
    if (!m) return null;
    const memFrac = m.memUsedMB != null && m.memTotalMB ? m.memUsedMB / m.memTotalMB : null;
    const diskFrac = m.diskFreeGB != null && m.diskTotalGB ? 1 - m.diskFreeGB / m.diskTotalGB : null;
    const hot = (m.tempC ?? 0) >= 80 || m.throttled;
    const storage = g<{ freeGB: number | null; minutes: number | null }>('status.storage');
    const program = g<{ uptime: number | null; restarts: number | null;
      version: { commit: string; deployedAt: string | null; dirty: boolean | null; source: string } | null }>('status.program');
    const v = program?.version;
    return (
      <section className="card" aria-label="机器">
        <SecHead no="05" name="机器" ind={hot ? 'warn' : 'ok'} />
        <div style={{ display: 'grid', gridTemplateColumns: '124px minmax(0, 1fr)', gap: 12, alignItems: 'center' }}>
          <Gauge value={m.tempC} max={100} limit={80} width={124} text={m.tempC == null ? '—' : `${Math.round(m.tempC)}°`}
            label={m.tempC == null ? '温度未知' : `温度 ${m.tempC} 摄氏度，红线是 80 度`} />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div><KV k="内存" v={m.memUsedMB != null ? `${(m.memUsedMB / 1024).toFixed(1)} / ${((m.memTotalMB ?? 0) / 1024).toFixed(1)} GB` : '—'} /><Segments frac={memFrac} /></div>
            <div><KV k="存储空间" v={m.diskFreeGB != null ? `${Math.round(m.diskFreeGB)} GB 可用` : '—'} /><Segments frac={diskFrac} warn={0.9} /></div>
            <KV k="还能录" v={storage?.minutes != null ? minutesText(storage.minutes) : '—'} />
            <div data-cpu="program">
              <KV k="主机程序 CPU" v={m.programCpu != null ? `${Math.round(m.programCpu)}% · 单核` : '—'} />
              <Segments frac={m.programCpu != null ? Math.min(1, m.programCpu / 100) : null} warn={0.85} />
            </div>
            <div data-cpu="machine">
              <KV k="整机 CPU" v={m.cpu != null ? `${Math.round(m.cpu)}%${m.cores ? ` · ${m.cores} 核` : ''}` : '—'} />
              <Segments frac={m.cpu != null ? m.cpu / 100 : null} warn={0.85} />
            </div>
          </div>
        </div>
        {(m.programCpuHistory?.length ?? 0) > 1 && (
          <>
            <Spark values={m.programCpuHistory!} max={100} height={38} />
            <span className="small">主机程序 CPU · 最近 1 分钟 · 按单核算，持续超过 90% 时声音和灯光可能卡顿</span>
          </>
        )}
        <div>
          <KV k="机器" v={m.model ?? m.host} />
          <KV k="降频" v={m.throttled == null ? '—' : m.throttled ? '有' : '无'} />
          <KV k="机器已运行" v={m.uptime != null ? duration(m.uptime) : '—'} />
          <KV k="主机程序已运行" v={program?.uptime != null ? duration(program.uptime) : '—'} />
          <KV k="自动重启" v={program?.restarts == null ? '未知' : `${program.restarts} 次`} />
          <KV k="版本" v={v ? `${v.commit}${v.dirty ? ' · 有未提交的改动' : ''}${v.deployedAt ? ` · 部署于 ${v.deployedAt.slice(0, 16).replace('T', ' ')}` : ''}` : '未知'} />
        </div>
      </section>
    );
  }
}

type NetKind = 'phoneHotspot' | 'selfHotspot' | 'external' | 'wired';
const NET_KIND: Record<NetKind, string> = {
  phoneHotspot: '手机热点', selfHotspot: '自建热点', external: '外部网络', wired: '有线网络',
};

interface Rate { actual: number | null; expected: number | null }

/** 各条链路的实际帧率，与期望值并排（期望为“最多”的，是只在有变化时才产生的数据） */
const RATE_ROWS: { key: string; label: string; upTo?: boolean }[] = [
  { key: 'sensing', label: '传感（控制器 → 主机）' },
  { key: 'perception', label: '垫面解读' },
  { key: 'beat', label: '声音化节拍' },
  { key: 'light', label: '灯光引擎' },
  { key: 'ledWrites', label: '写给控制器的灯光' },
  { key: 'pushMat', label: '推送到控制台 · 垫面', upTo: true },
  { key: 'pushLeds', label: '推送到控制台 · 灯环', upTo: true },
];

function RhythmSection() {
  const s = useConsole();
  const rates = getPath<Record<string, Rate | null>>(s.state, 'status.rates') ?? {};
  const t = getPath<{ stalls: number | null; stallsRecent: number | null;
    maxLagMs: number | null; late: number | null; lateRecent: number | null; yields: number | null; rejected: number | null;
    synthLate?: number | null; stallsAttention?: boolean; lateAttention?: boolean; synthLateAttention?: boolean }>(s.state, 'status.timing');
  // 迟到的定时声音：合成器服务收到得太晚的（只能在下一个音频缓冲执行）加上主机来不及交出、直接丢弃的
  const late = t == null || (t.synthLate == null && t.lateRecent == null) ? null : (t.synthLate ?? 0) + (t.lateRecent ?? 0);
  const display = useDisplayFps();
  const rows = RATE_ROWS.map((r) => ({ ...r, rate: rates[r.key] ?? null }))
    .filter((r) => r.rate && (r.rate.actual !== null || r.rate.expected !== null));
  return (
    <section className="card" aria-label="节奏">
      <SecHead no="03" name="节奏" />
      <div className="rate-table" role="table" aria-label="各条链路的帧率">
        <div className="rate-row head" role="row">
          <span role="columnheader">链路</span><span role="columnheader">实测</span><span role="columnheader">期望</span>
        </div>
        {rows.map(({ key, label, upTo, rate }) => {
          const low = !upTo && rate!.expected && rate!.actual !== null && rate!.actual < rate!.expected * 0.9;
          return (
            <div key={key} className="rate-row" role="row" data-rate={key}>
              <span role="cell">{label}</span>
              <span role="cell" className="num" style={low ? { color: 'var(--amber-line)' } : undefined}>{fps(rate!.actual)}</span>
              <span role="cell" className="num dim">{rate!.expected ? `${upTo ? '最多 ' : ''}${rate!.expected}` : '—'}</span>
            </div>
          );
        })}
        <div className="rate-row" role="row" data-rate="display">
          <span role="cell">本机控制台显示</span>
          <span role="cell" className="num">{fps(display)}</span>
          <span role="cell" className="num dim">60</span>
        </div>
      </div>
      <span className="small">单位：次/秒。垫面和灯环只在有变化时推送，静止时为 0 属于正常。</span>
      <div className="grid2">
        <Tile label="节拍延迟" value={t?.maxLagMs == null ? '—' : Math.round(t.maxLagMs)} unit={t?.maxLagMs == null ? '' : 'ms · 最近 1 分钟最大'}
          sub={t?.stallsRecent == null ? undefined
            : `超过 50 ms ${t.stallsRecent} 次`}
          tone={t?.stallsAttention ? 'warn' : t ? 'ok' : undefined} />
        <Tile label="定时声音迟到" value={late ?? '—'} unit={late == null ? '' : '次 · 最近 1 分钟'}
          sub={t == null ? undefined : `合成器收到太晚 ${t.synthLate ?? '—'} · 主机丢弃 ${t.lateRecent ?? '—'}`}
          tone={t?.synthLateAttention || t?.lateAttention ? 'warn' : t ? 'ok' : undefined} />
        <Tile label="声部让位" value={t?.yields ?? '—'} unit={t?.yields == null ? '' : '次'} sub="为新声部腾出位置" />
        <Tile label="因预算放弃" value={t?.rejected ?? '—'} unit={t?.rejected == null ? '' : '次'} sub="声部超过上限没能发声" />
      </div>
    </section>
  );
}

/** 本机浏览器实际的显示帧率（requestAnimationFrame 每秒的次数），只反映正在看看板的这台设备 */
function useDisplayFps(): number | null {
  const [value, setValue] = useState<number | null>(null);
  useEffect(() => {
    if (typeof requestAnimationFrame !== 'function') return;
    let frames = 0;
    let id = 0;
    let start = performance.now();
    const loop = (now: number) => {
      frames++;
      if (now - start >= 1000) {
        setValue(Math.round((frames * 1000) / (now - start)));
        frames = 0;
        start = now;
      }
      id = requestAnimationFrame(loop);
    };
    id = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(id);
  }, []);
  return value;
}

/** 两条每秒一个点的曲线按末尾对齐，逐点取较高的（谁先撑不住看谁） */
function maxTail(a: number[], b: number[]): number[] {
  const n = Math.max(a.length, b.length);
  const out: number[] = [];
  for (let i = 0; i < n; i++) {
    const x = a[a.length - n + i];
    const y = b[b.length - n + i];
    out.push(Math.max(x ?? 0, y ?? 0));
  }
  return out;
}

function fps(v: number | null | undefined): string {
  return v === null || v === undefined ? '—' : String(Math.round(v));
}

function minutesText(min: number): string {
  return min >= 120 ? `约 ${Math.floor(min / 60)} 小时` : `约 ${min} 分钟`;
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
