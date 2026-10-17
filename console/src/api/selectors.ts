/** 从状态树里取控制台需要的数据。路径见 docs/implementation/CONTROL_API.md。 */
import type { ConsoleState } from './client';
import { getPath } from './patch';

export interface ArrangementItem {
  id: string;
  title: string;
  mode: string;
  modeLabel: string;
  description: string;
  ringLabels: string[];
  missing: string[];
  error: string | null;
}

export interface ModeStatus {
  text: string;
  reading: string | null;
  transport: string | null;
}

export interface LogItem {
  at: number;
  level: 'info' | 'warning' | 'error';
  text: string;
  count?: number;
}

export interface Levels {
  /** 总输出各声道电平（dBFS） */
  output: number[];
  /** 每环 [左, 右] 电平（dBFS） */
  rings: [number, number][];
}

export const arrangements = (s: ConsoleState) =>
  getPath<ArrangementItem[]>(s.state, 'catalog.arrangements') ?? [];

export const currentId = (s: ConsoleState) => getPath<string | null>(s.state, 'status.current.arrangement') ?? null;

export const current = (s: ConsoleState) => {
  const id = currentId(s);
  return arrangements(s).find((a) => a.id === id) ?? null;
};

export const modeStatus = (s: ConsoleState) => getPath<ModeStatus | null>(s.state, 'status.current.modeStatus') ?? null;

export const switching = (s: ConsoleState) =>
  getPath<{ from: string | null; to: string; progress: number } | null>(s.state, 'status.current.switching') ?? null;

export const isVirtual = (s: ConsoleState) => getPath<boolean>(s.state, 'status.current.virtual') === true;

export const logs = (s: ConsoleState) => getPath<LogItem[]>(s.state, 'status.log') ?? [];

export const setting = <T,>(s: ConsoleState, path: string) => getPath<T>(s.state, `settings.${path}`);

export const levels = (s: ConsoleState): Levels | null => (s.streams.levels as unknown as Levels) ?? null;

export function transportWord(st: ModeStatus | null): string {
  if (st?.transport === 'idle') return '空闲';
  if (st?.transport === 'ended') return '曲终';
  return '演奏中';
}

export function dbText(db: number | undefined): string {
  if (db === undefined || db <= -59.5) return '—';
  return `−${Math.abs(Math.round(db))}`.replace('−0', '0');
}

export type Level = 'ok' | 'warn' | 'error' | 'unknown';

export interface Health {
  sound: { level: Level; reason: string };
  mat: { level: Level; reason: string };
  net: { level: Level; reason: string };
  overall: Level;
  issues: string[];
}

export const health = (s: ConsoleState) => getPath<Health>(s.state, 'status.health') ?? null;

export const LOOK: Record<Level, { text: string; sq: string; tag: string; dashed?: boolean }> = {
  ok: { text: '正常', sq: 'var(--green)', tag: 'var(--green-t)' },
  warn: { text: '需要注意', sq: 'var(--amber)', tag: 'var(--amber-t)' },
  error: { text: '异常', sq: 'var(--red)', tag: 'var(--red-t)' },
  unknown: { text: '未知', sq: 'transparent', tag: 'var(--text-2)', dashed: true },
};

/** 页面顶部的提示条：只在需要注意或异常时出现，写出第一条原因 */
export function alertOf(h: Health | null): { level: Level; text: string } | null {
  if (!h || (h.overall !== 'warn' && h.overall !== 'error') || !h.issues.length) return null;
  return { level: h.overall, text: h.issues[0] };
}

export interface RecordingStatus {
  state: 'idle' | 'countdown' | 'recording';
  count?: number | null;
  flash?: boolean;
  elapsed?: number;
  folder?: string;
  audio?: boolean;
  freeGB?: number;
}

export interface RecordingItem {
  name: string;
  startedAt: string | null;
  title: string;
  duration: number | null;
  audio: boolean;
}

export const recording = (s: ConsoleState) =>
  getPath<RecordingStatus>(s.state, 'status.recording') ?? { state: 'idle' as const };

export const recordings = (s: ConsoleState) => getPath<RecordingItem[]>(s.state, 'catalog.recordings') ?? [];

export function clockText(sec: number): string {
  const t = Math.max(0, Math.floor(sec));
  const h = Math.floor(t / 3600);
  const m = Math.floor((t % 3600) / 60);
  const ss = t % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return (h ? `${p(h)}:` : '') + `${p(m)}:${p(ss)}`;
}
