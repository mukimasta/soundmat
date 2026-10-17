import { useConsole } from '../api/context';
import { getPath } from '../api/patch';
import { Sheet } from '../components/Sheet';

const chevron = (
  <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#8F887C" strokeWidth="1.8"
    strokeLinecap="round" strokeLinejoin="round"><path d="M9.5 6l6 6-6 6" /></svg>
);

/** 菜单：已录制与设置。 */
export function MenuSheet({ onClose, onOpen, recordingsText }: {
  onClose: () => void;
  onOpen: (sheet: 'recs' | 'set') => void;
  recordingsText?: string;
}) {
  const s = useConsole();
  const host = getPath<string>(s.state, 'status.machine.host');
  const model = getPath<string>(s.state, 'status.machine.model');
  return (
    <Sheet title="菜单" onClose={onClose}>
      <div className="menu-list">
        {recordingsText !== undefined && (
          <>
            <button type="button" onClick={() => onOpen('recs')}>
              <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7">
                <circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="3.2" fill="currentColor" />
              </svg>
              <span className="grow">已录制</span>
              <span className="mono-sub">{recordingsText}</span>
              {chevron}
            </button>
            <div className="sep" />
          </>
        )}
        <button type="button" onClick={() => onOpen('set')}>
          <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
            <path d="M4 7h10 M18 7h2 M4 17h4 M12 17h8" /><circle cx="16" cy="7" r="2.2" /><circle cx="10" cy="17" r="2.2" />
          </svg>
          <span className="grow">设置</span>
          {chevron}
        </button>
      </div>
      {(host || model) && <p className="foot">{[host, model].filter(Boolean).join(' · ')}</p>}
    </Sheet>
  );
}
