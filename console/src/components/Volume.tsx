import { useRef, useState } from 'react';
import { useClient, useConsole } from '../api/context';
import * as sel from '../api/selectors';

/** 总音量（设置 sound.volume）：首页上不显眼的一行。拖动时本地先变，停下 120 ms 后再发给主机程序。 */
export function Volume() {
  const s = useConsole();
  const client = useClient();
  const stored = sel.setting<number>(s, 'sound.volume') ?? 0.8;
  const [local, setLocal] = useState<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const value = Math.round((local ?? stored) * 100);
  const send = (v: number) => {
    setLocal(v);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      void client.post('/api/settings', { changes: { 'sound.volume': v } }).finally(() => setLocal(null));
    }, 120);
  };
  return (
    <div className="volume">
      <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
        strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" />
        <path d="M15.5 9a4.2 4.2 0 0 1 0 6" />
      </svg>
      <input aria-label="总音量" type="range" min={0} max={100} step={1} value={value}
        onChange={(e) => send(Number(e.target.value) / 100)} />
      <span className="val">{value}%</span>
    </div>
  );
}
