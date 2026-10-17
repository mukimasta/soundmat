/**
 * 与主机程序的连接：一条 WebSocket 接收状态（完整快照 + 变化），HTTP 发送命令。
 * 断开时清空所有实时数据，界面显示“已断开”而不是过时的数据；之后自动重连。
 */
import { applyChanges, type Tree } from './patch';
import type { ConfigRow, MatMsg, ServerMsg, Zone } from './types';

export interface ConsoleState {
  connected: boolean;
  geometry: Zone[];
  config: ConfigRow[];
  ledCount: number;
  state: Tree;
  mat: MatMsg | null;
  /** 其他高频数据（如灯环预览），按消息类型保存最新一条 */
  streams: Record<string, Record<string, unknown>>;
}

export const initialState: ConsoleState = {
  connected: false,
  geometry: [],
  config: [],
  ledCount: 0,
  state: {},
  mat: null,
  streams: {},
};

export function reduce(s: ConsoleState, msg: ServerMsg): ConsoleState {
  switch (msg.type) {
    case 'hello': {
      const m = msg as Extract<ServerMsg, { type: 'hello' }>;
      return { ...s, connected: true, geometry: m.geometry, config: m.config, ledCount: m.ledCount, state: m.state };
    }
    case 'patch':
      return { ...s, state: applyChanges(s.state, (msg as Extract<ServerMsg, { type: 'patch' }>).changes) };
    case 'mat':
      return { ...s, mat: msg as MatMsg };
    default: {
      const { type, ...rest } = msg as { type: string } & Record<string, unknown>;
      return { ...s, streams: { ...s.streams, [type]: rest } };
    }
  }
}

type Listener = () => void;

export class SoundMatClient {
  private s: ConsoleState = initialState;
  private listeners = new Set<Listener>();
  private socket: WebSocket | null = null;
  private retry: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;

  constructor(private readonly base: string = '') {}

  getState = (): ConsoleState => this.s;

  subscribe = (fn: Listener): (() => void) => {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  };

  private set(next: ConsoleState) {
    this.s = next;
    this.listeners.forEach((fn) => fn());
  }

  handle(msg: ServerMsg) {
    this.set(reduce(this.s, msg));
  }

  connect() {
    this.stopped = false;
    const url = wsUrl(this.base);
    const sock = new WebSocket(url);
    this.socket = sock;
    sock.onmessage = (e) => this.handle(JSON.parse(e.data) as ServerMsg);
    sock.onclose = () => {
      if (this.socket !== sock) return;
      this.socket = null;
      this.set({ ...this.s, connected: false, mat: null, streams: {} });
      if (!this.stopped) this.retry = setTimeout(() => this.connect(), 1000);
    };
    sock.onerror = () => sock.close();
  }

  close() {
    this.stopped = true;
    if (this.retry) clearTimeout(this.retry);
    this.socket?.close();
  }

  async get(path: string): Promise<unknown> {
    const r = await fetch(this.base + path);
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return r.json();
  }

  async post(path: string, body?: unknown): Promise<unknown> {
    const r = await fetch(this.base + path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok) {
      const detail = await r.json().then((j) => j?.detail).catch(() => null);
      throw new Error(typeof detail === 'string' ? detail : `${path}: ${r.status}`);
    }
    return r.json();
  }

  toggleZone = (zone: number) => this.post('/api/virtual/toggle', { zone });
  clearVirtual = () => this.post('/api/virtual/clear');
}

function wsUrl(base: string): string {
  if (base) return base.replace(/^http/, 'ws') + '/ws';
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}/ws`;
}
