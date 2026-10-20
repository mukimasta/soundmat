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

/** 垫面上的一颗石头：主区、按压力加权的位置（半径为绘图单位，角度 0° 在 12 点、顺时针）、总压力 */
export interface StoneMsg {
  id: number;
  zone: number;
  r: number;
  a: number;
  s: number;
}

export interface MatMsg {
  type: 'mat';
  t: number;
  source: 'controller' | 'virtual';
  /** 每个区域的压力，0–1000 */
  pressure: number[];
  /** 每颗石头的主区 */
  occupied: number[];
  stones?: StoneMsg[];
  ringCounts: number[];
  control: number | null;
}

export type ServerMsg = HelloMsg | PatchMsg | MatMsg | ({ type: string } & Record<string, unknown>);
