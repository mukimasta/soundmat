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
            {SoundCard({ h })}
            {MatCard({ h })}
            {NetCard({ h })}
            {MachineCard()}
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
        {s.connected && Details()}
      </div>
    </>
  );

  /** 声音：听到的结果（电平、负载、卡顿、迟到）和声道测试；配置不一致或缺东西时才出现提示。 */
  function SoundCard({ h }: { h: sel.Health | null }) {
    const synth = g<Synth>('status.audio.synth');
    const lv = sel.levels(s);
    const names = layoutNames();
    const out = lv?.output ?? [];
    const load = soundLoad();
    const xruns = g<number | null>('status.audio.xruns');
    const t = timing();
    const late = lateCount(t);
    const rate = synth?.sampleRate;
    const missing = g<string[]>('status.assets.missing') ?? [];
    const dev = g<{ name: string; usb: boolean } | null>('status.audio.outputDevice');
    return (
      <section className="card" aria-label="声音">
        <SecHead no="01" name="声音" ind={h?.sound.level} />
        <div style={{ display: 'grid', gridTemplateColumns: 'auto minmax(0, 1fr)', gap: 8 }}>
          <div className="vu-col">
            <VuMeter levels={out.length ? out : names.map(() => -120)} names={names} />
            <span className="vu-vals">{(out.length ? out : names.map(() => undefined)).map((l, i) => <span key={i}>{sel.dbText(l)}</span>)}</span>
            <span className="vu-vals" style={{ fontFamily: 'var(--font)', fontWeight: 400, color: 'var(--text-2)' }}>
              {names.map((n, i) => <span key={i}>{n}</span>)}
            </span>
          </div>
          <div className="load-col">
            <span className="small" style={{ fontSize: 12 }}>
              运算负载{load.who ? ` · ${load.who === 'program' ? '主机程序' : '合成器'}` : ''}
            </span>
            <Gauge value={load.value === null ? null : Math.min(load.value, 100)} max={100} limit={85}
              text={load.value === null ? '—' : `${Math.round(load.value)}%`}
              label={load.value === null ? '运算负载未知'
                : `运算负载 ${Math.round(load.value)}%，来自${load.who === 'program' ? '主机程序' : '合成器'}，红线是上限 85%`} />
            <Spark values={load.history} max={100} />
            <span className="small">最近 1 分钟 · 合成器和主机程序中较高的</span>
          </div>
        </div>
        <div className="grid2">
          <Tile label={g<boolean>('status.audio.xrunsSinceStart') ? '卡顿 · 启动以来' : '卡顿 · 最近 1 小时'}
            value={xruns ?? '—'} unit={xruns == null ? '' : '次'}
            sub={xruns == null ? '无法读取' : xruns ? `${CROSS}声音断过` : `${CHECK}没有断过`} tone={xruns ? 'warn' : xruns === 0 ? 'ok' : undefined} />
          <Tile label="迟到 · 最近 1 分钟" value={late ?? '—'} unit={late == null ? '' : '次'}
            sub={late == null ? undefined : late ? `${CROSS}有音没按时响` : `${CHECK}每个音都准时`}
            tone={t?.synthLateAttention || t?.lateAttention ? 'warn' : late === 0 ? 'ok' : undefined} />
        </div>
        {dev && !dev.usb && <Problem error text={`合成器输出到 ${dev.name}，不是 USB 声卡，音箱不会发声`} />}
        {synth?.synthdefsLoaded === false && <Problem error text="合成器服务没有加载音色，需要先编译音色" />}
        {rate && Math.abs(rate - 48000) >= 1 && <Problem text={`采样率是 ${rate / 1000} kHz，期望 48 kHz`} />}
        {missing.length > 0 && (
          <Problem text={`当前编排缺少 ${missing.length} 个声音素材，用到它们的声音不会发声`}>
            {missing.map((m) => <span key={m} style={{ fontFamily: 'var(--mono)', fontWeight: 400, overflowWrap: 'anywhere' }}>{m}</span>)}
          </Problem>
        )}
        <ToneButtons names={names} />
      </section>
    );
  }

  /** 垫子：传感帧率和控制器是否连着。 */
  function MatCard({ h }: { h: sel.Health | null }) {
    const m = mat();
    const virtual = m?.source === 'virtual';
    const hist = g<number[]>('status.matHistory') ?? [];
    return (
      <section className="card" aria-label="垫子">
        <SecHead no="02" name="垫子" ind={h?.mat.level} />
        {virtual ? (
          <span style={{ fontSize: 16, fontWeight: 600 }}>虚拟垫子</span>
        ) : (
          <>
            <span><span className="big-num">{m?.fps == null ? '—' : m.fps.toFixed(1)}</span>
              <span className="small" style={{ marginLeft: 6 }}>fps · 传感帧率</span></span>
            <Spark values={hist} max={80} height={38} />
            <KV k="控制器" v={m?.connected ? `已连接 · ${m.port ?? ''}` : '未连接'} />
            {m && !m.connected && m.problem && <Problem error text={m.problem} />}
          </>
        )}
      </section>
    );
  }

  /** 网络：连着什么、从哪里能打开控制台。 */
  function NetCard({ h }: { h: sel.Health | null }) {
    const n = g<{ name: string | null; address: string | null; tailscale: string | null; tailscaleAddress: string | null;
      localName: string | null; kind: NetKind | null; apClients: number | null }>('status.network');
    const kind = n?.kind ? NET_KIND[n.kind] : null;
    return (
      <section className="card" aria-label="网络">
        <SecHead no="03" name="网络" ind={h?.net.level} />
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

  /** 机器：温度、内存与存储、还能录多久、CPU，以及运行时间、自动重启和版本（照看装置时常看，不收起）。 */
  function MachineCard() {
    const m = machine();
    if (!m) return null;
    const memFrac = m.memUsedMB != null && m.memTotalMB ? m.memUsedMB / m.memTotalMB : null;
    const diskFrac = m.diskFreeGB != null && m.diskTotalGB ? 1 - m.diskFreeGB / m.diskTotalGB : null;
    const hot = (m.tempC ?? 0) >= 80 || !!m.throttled;
    const storage = g<{ freeGB: number | null; minutes: number | null }>('status.storage');
    const program = g<{ uptime: number | null; restarts: number | null;
      version: { commit: string; deployedAt: string | null; dirty: boolean | null; source: string } | null }>('status.program');
    const v = program?.version;
    return (
      <section className="card" aria-label="机器">
        <SecHead no="04" name="机器" ind={hot ? 'warn' : 'ok'} />
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
        {m.throttled && <Problem text="正在降频（供电不足或过热），声音和灯光可能变慢" />}
        <div>
          <KV k="机器" v={m.model ?? m.host} />
          <KV k="降频" v={m.throttled == null ? '—' : m.throttled ? '有' : '无'} tone={m.throttled ? 'warn' : undefined} />
          <KV k="系统时间" v={m.clockSynced == null ? '—' : m.clockSynced ? '开机时已校准' : '未校准（开机时没网，录音的日期时间可能不准）'}
            tone={m.clockSynced === false ? 'warn' : undefined} />
          <KV k="机器已运行" v={m.uptime != null ? duration(m.uptime) : '—'} />
          <KV k="主机程序已运行" v={program?.uptime != null ? duration(program.uptime) : '—'} />
          <KV k="自动重启" v={program?.restarts == null ? '未知' : `${program.restarts} 次`} />
          <KV k="版本" v={v ? `${v.commit}${v.dirty ? ' · 有未提交的改动' : ''}${v.deployedAt ? ` · 部署于 ${v.deployedAt.slice(0, 16).replace('T', ' ')}` : ''}` : '未知'} />
        </div>
      </section>
    );
  }

  /** 详细信息：配置、各条链路和内部计数，默认收起，排查问题时打开。 */
  function Details() {
    const synth = g<Synth>('status.audio.synth');
    const names = layoutNames();
    const rate = synth?.sampleRate;
    const channels = g<number>('status.audio.channels');
    const buffer = g<{ period: number; periods: number; driver: string } | null>('status.audio.buffer');
    const missing = g<string[]>('status.assets.missing') ?? [];
    const needed = g<number>('status.assets.needed') ?? 0;
    const dev = g<{ name: string; usb: boolean } | null>('status.audio.outputDevice');
    const engine = g<{ voices: number; budget: number }>('status.engine');
    const load = soundLoad();
    const t = timing();
    const mt = mat();
    return (
      <details className="details">
        <summary>
          <span className="t">详细信息<span className="hint">音频配置、各条链路和内部计数</span></span>
          <svg className="chev" width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
            strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round"><path d="M6.5 9.5L12 15l5.5-5.5" /></svg>
        </summary>
        <div className="groups">
          <section aria-label="音频">
            <span className="grp">音频</span>
            <KV k="输出设备" v={dev ? (dev.usb ? `USB 声卡 · ${dev.name.split(' - ').pop()}` : dev.name) : '未知'} tone={dev && !dev.usb ? 'error' : undefined} />
            <KV k="采样率" v={rate ? `${rate / 1000} kHz` : '—'} tone={rate && Math.abs(rate - 48000) >= 1 ? 'warn' : undefined} />
            <KV k="声道" v={channels ? `${channels} · ${names.join(' · ')}` : '—'} />
            <KV k="缓冲" v={buffer ? `${buffer.period} × ${buffer.periods ?? '?'} · ${buffer.driver}` : '—'} />
            <KV k="音色" v={synth?.synthdefsLoaded === false ? '没有加载' : synth?.synthdefsLoaded ? '全部加载' : '—'} tone={synth?.synthdefsLoaded === false ? 'error' : undefined} />
            <KV k="声音素材" v={needed ? `${needed - missing.length} / ${needed}` : '当前编排不用素材'} tone={missing.length ? 'warn' : undefined} />
            <KV k="在响声部" v={engine ? `${engine.voices} / ${engine.budget}` : '—'} />
            <KV k="运算负载" v={`合成器 ${pct(load.synth)} · 主机程序 ${pct(load.program)}（单核）`} />
          </section>
          <RhythmGroup t={t} />
          <section aria-label="垫子详情">
            <span className="grp">垫子</span>
            <KV k="输入" v={mt?.source === 'virtual' ? '虚拟垫子' : '压力垫控制器'} />
            <KV k="校验错误" v={mt?.source === 'virtual' || mt?.checksumErrors == null ? '—' : String(mt.checksumErrors)} />
          </section>
        </div>
      </details>
    );
  }

  function layoutNames(): string[] {
    const layout = sel.setting<{ azimuths: number[]; names: string[] }>(s, 'sound.layout');
    return layout?.names?.length ? layout.names : ['左', '右'];
  }

  /** 运算负载：合成器（scsynth 自报）和主机程序（占单核）里更高的那个，也就是先撑不住的一方 */
  function soundLoad() {
    const synth = g<Synth>('status.audio.synth')?.avgLoad ?? null;
    const program = g<number | null>('status.machine.programCpu') ?? null;
    const who: 'synth' | 'program' | null = synth === null && program === null ? null
      : (program ?? -1) > (synth ?? -1) ? 'program' : 'synth';
    const history = maxTail(g<number[]>('status.audio.loadHistory') ?? [], g<number[]>('status.machine.programCpuHistory') ?? []);
    return { synth, program, who, value: who === 'program' ? program : synth, history };
  }

  function timing() {
    return g<Timing>('status.timing');
  }

  function mat() {
    return g<{ source: string; connected: boolean | null; port: string | null; fps: number | null;
      checksumErrors: number | null; problem: string | null }>('status.mat');
  }

  function machine() {
    return g<{ host: string; model: string | null; tempC: number | null; throttled: boolean | null; memUsedMB: number | null;
      memTotalMB: number | null; diskFreeGB: number | null; diskTotalGB: number | null; uptime: number | null; programUptime: number;
      programCpu?: number | null; cpu?: number | null; cores?: number | null; programCpuHistory?: number[];
      clockSynced?: boolean | null }>('status.machine');
  }
}

interface Timing {
  stalls: number | null; stallsRecent: number | null; maxLagMs: number | null; late: number | null; lateRecent: number | null;
  yields: number | null; rejected: number | null; synthLate?: number | null;
  stallsAttention?: boolean; lateAttention?: boolean; synthLateAttention?: boolean;
}

/** 迟到的定时声音：合成器服务收到得太晚的（只能在下一个音频缓冲执行）加上主机来不及交出、直接丢弃的 */
function lateCount(t: Timing | undefined): number | null {
  if (t == null || (t.synthLate == null && t.lateRecent == null)) return null;
  return (t.synthLate ?? 0) + (t.lateRecent ?? 0);
}

function pct(v: number | null): string {
  return v === null ? '—' : `${Math.round(v)}%`;
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

/** 节奏：各条链路的实测帧率与期望值、节拍延迟和声音引擎的内部计数 */
function RhythmGroup({ t }: { t: Timing | undefined }) {
  const s = useConsole();
  const rates = getPath<Record<string, Rate | null>>(s.state, 'status.rates') ?? {};
  const display = useDisplayFps();
  const rows = RATE_ROWS.map((r) => ({ ...r, rate: rates[r.key] ?? null }))
    .filter((r) => r.rate && (r.rate.actual !== null || r.rate.expected !== null));
  return (
    <section aria-label="节奏">
      <span className="grp">节奏</span>
      <div className="rate-table" role="table" aria-label="各条链路的帧率">
        <div className="rate-row head" role="row">
          <span role="columnheader">链路（次/秒）</span><span role="columnheader">实测</span><span role="columnheader">期望</span>
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
      <span className="small">垫面和灯环只在有变化时推送，静止时为 0 属于正常。</span>
      <KV k="节拍延迟" v={t?.maxLagMs == null ? '—' : `最大 ${Math.round(t.maxLagMs)} ms · 超过 50 ms ${t.stallsRecent ?? 0} 次`}
        tone={t?.stallsAttention ? 'warn' : undefined} />
      <KV k="合成器收到太晚" v={t?.synthLate == null ? '—' : `${t.synthLate} 次`} tone={t?.synthLateAttention ? 'warn' : undefined} />
      <KV k="主机来不及、丢弃" v={t?.lateRecent == null ? '—' : `${t.lateRecent} 次`} tone={t?.lateAttention ? 'warn' : undefined} />
      <KV k="声部让位" v={t?.yields == null ? '—' : `${t.yields} 次`} />
      <KV k="因预算放弃" v={t?.rejected == null ? '—' : `${t.rejected} 次`} />
      <span className="small">节拍延迟和迟到是最近 1 分钟；让位（为新声部腾位置）和放弃（超过声部上限没能发声）是启动以来。</span>
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

function KV({ k, v, tone }: { k: string; v: string; tone?: 'warn' | 'error' }) {
  const color = tone === 'error' ? 'var(--red-line)' : tone === 'warn' ? 'var(--amber-line)' : undefined;
  return <div className="kv"><span>{k}</span><span style={color ? { color } : undefined}>{v}</span></div>;
}

/** 出问题时才出现的一条提示（例如缺素材、输出设备不对）：平时不占位置 */
function Problem({ text, error, children }: { text: string; error?: boolean; children?: React.ReactNode }) {
  return (
    <div className={error ? 'problem error' : 'problem'} role="note">
      <span>{CROSS}{text}</span>
      {children}
    </div>
  );
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
