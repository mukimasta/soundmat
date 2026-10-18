import { useRef, useState } from 'react';
import { useClient, useConsole } from '../api/context';
import * as sel from '../api/selectors';

/** 总音量（设置 sound.volume）：拖动时本地先变，停下 120 ms 后再发给主机程序。 */
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
      <span className="head"><label htmlFor="vol">总音量</label><span>{value}%</span></span>
      <input id="vol" type="range" min={0} max={100} step={1} value={value}
        onChange={(e) => send(Number(e.target.value) / 100)} />
    </div>
  );
}
