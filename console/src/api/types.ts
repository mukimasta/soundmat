/** 控制接口的消息格式，见 docs/implementation/CONTROL_API.md。 */
import type { Tree } from './patch';

export interface Zone {
  index: number;
  id: string;
  ring: number;
  slot: number;
  center: number;
  span: number;
  rInner: number;
  rOuter: number;
}

export interface ConfigRow {
  label: string;
  value: string;
}

export interface HelloMsg {
  type: 'hello';
  geometry: Zone[];
  config: ConfigRow[];
  ledCount: number;
  state: Tree;
}

export interface PatchMsg {
  type: 'patch';
  changes: [string, unknown][];
}

export interface MatMsg {
  type: 'mat';
  t: number;
  source: 'controller' | 'virtual';
  /** 每个区域的压力，0–1000 */
  pressure: number[];
  occupied: number[];
  ringCounts: number[];
  control: number | null;
}

export type ServerMsg = HelloMsg | PatchMsg | MatMsg | ({ type: string } & Record<string, unknown>);
