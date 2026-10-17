interface Props {
  onDash: () => void;
  onMenu: () => void;
  dot: string | null;
  dashLabel: string;
  record: { label: string; aria: string; disabled: boolean; onPress: () => void; inner: 'idle' | 'stop' | number };
  segments?: { d: string; color: string }[];
}

/** 底部三个入口：看板、录制、菜单（设计稿）。 */
export function BottomNav({ onDash, onMenu, dot, dashLabel, record, segments = [] }: Props) {
  return (
    <nav className="nav" aria-label="主要操作">
      <button type="button" className="nav-btn start" onClick={onDash} aria-label={dashLabel}>
        <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
          <rect x="3.5" y="3.5" width="7" height="7" rx="1.8" /><rect x="13.5" y="3.5" width="7" height="7" rx="1.8" />
          <rect x="3.5" y="13.5" width="7" height="7" rx="1.8" /><rect x="13.5" y="13.5" width="7" height="7" rx="1.8" />
        </svg>
        <span>看板</span>
        {dot && <span className="nav-dot" aria-hidden="true" style={{ background: dot }} />}
      </button>
      <div className="rec">
        <div className="rec-ring">
          <svg width="78" height="78" viewBox="-50 -50 100 100" aria-hidden="true">
            <circle r="45" fill="none" stroke="#2E2C27" strokeWidth="5" />
            {segments.map((g, i) => <path key={i} d={g.d} stroke={g.color} fill="none" strokeWidth="5" strokeLinecap="round" />)}
          </svg>
          <button type="button" className="rec-btn" aria-label={record.aria} disabled={record.disabled}
            onClick={record.onPress} style={{ background: 'var(--red)' }}>
            {record.inner === 'idle' && <span style={{ width: 20, height: 20, borderRadius: '50%', background: '#fff' }} />}
            {record.inner === 'stop' && <span style={{ width: 18, height: 18, borderRadius: 4, background: '#fff' }} />}
            {typeof record.inner === 'number' && <span style={{ fontSize: 26, fontWeight: 700, lineHeight: 1 }}>{record.inner}</span>}
          </button>
        </div>
        <span className="rec-label" aria-live="polite">{record.label}</span>
      </div>
      <button type="button" className="nav-btn end" onClick={onMenu}>
        <svg width="24" height="24" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round">
          <path d="M4.5 7h15 M4.5 12h15 M4.5 17h15" />
        </svg>
        <span>菜单</span>
      </button>
    </nav>
  );
}
