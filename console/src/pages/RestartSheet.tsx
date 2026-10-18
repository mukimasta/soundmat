import { useState } from 'react';
import { useClient, useConsole } from '../api/context';
import { getPath } from '../api/patch';
import { Sheet } from '../components/Sheet';

type Target = 'sound' | 'program' | 'machine';

/** 从轻到重：先试重启声音，不行再重启程序，最后才重启机器。 */
const OPTIONS: { target: Target; title: string; text: string }[] = [
  { target: 'sound', title: '重启声音', text: '重新启动音频服务和合成器，声音中断约 5 秒。没声音、卡顿时先试这个。' },
  { target: 'program', title: '重启程序', text: '重新启动主机程序，声音和灯光中断约 15 秒，控制台会自己重新连上。' },
  { target: 'machine', title: '重启机器', text: '整台树莓派重新启动，约 1 分钟后回来。前两个都不管用时再用。' },
];

/** 重启：三个选项各有说明；点"重启"后按钮变成"确认重启"，再点一次才执行。 */
export function RestartSheet({ onClose, onBack }: { onClose: () => void; onBack: () => void }) {
  const s = useConsole();
  const client = useClient();
  const enabled = getPath<boolean>(s.state, 'status.maintenance.enabled') === true;
  const [armed, setArmed] = useState<Target | null>(null);
  const [done, setDone] = useState<Target | null>(null);
  const [error, setError] = useState<string | null>(null);

  const restart = async (target: Target) => {
    setArmed(null);
    setError(null);
    try {
      await client.post('/api/system/restart', { target });
      setDone(target);
    } catch (e) {
      // 重启程序或机器时连接会马上断开，请求可能拿不到回复：那是正常的
      if (target === 'sound') setError(String((e as Error).message ?? e));
      else setDone(target);
    }
  };

  return (
    <Sheet title="重启" onClose={onClose} onBack={onBack}>
      {!enabled && <p className="hint">这里不是由 systemd 运行的装置（例如开发机），不能从控制台重启。</p>}
      {done && <p className="hint" role="status">{OPTIONS.find((o) => o.target === done)!.title}中…</p>}
      {error && <p className="hint warn" role="alert">{error}</p>}
      {OPTIONS.map((o) => (
        <div key={o.target} className="rec-item restart-item" data-target={o.target}>
          <span className="np-text">
            <span className="arr-title" style={{ fontSize: 15 }}>{o.title}</span>
            <span className="arr-mode">{o.text}</span>
          </span>
          <button type="button" className={armed === o.target ? 'btn-clear danger' : 'btn-clear'} disabled={!enabled}
            onClick={() => (armed === o.target ? void restart(o.target) : setArmed(o.target))}>
            {armed === o.target ? '确认重启' : '重启'}
          </button>
        </div>
      ))}
    </Sheet>
  );
}
