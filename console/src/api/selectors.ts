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
