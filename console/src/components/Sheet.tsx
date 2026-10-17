import { useEffect, useRef, type ReactNode } from 'react';

interface Props {
  title: string;
  onClose: () => void;
  onBack?: () => void;
  children: ReactNode;
}

/**
 * 从底部升起的面板（设计稿的编排、菜单、已录制、设置）。
 * 打开时焦点移进面板，按 Esc 关闭，关闭后焦点回到打开它的按钮。
 */
export function Sheet({ title, onClose, onBack, children }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const close = useRef(onClose);
  close.current = onClose;

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        close.current();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      if (opener && opener.isConnected) opener.focus();
    };
  }, []);

  return (
    <div className="sheet-backdrop">
      <button type="button" className="close-area" aria-label="关闭面板" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref}>
        <div className="sheet-handle"><span /></div>
        <div className="sheet-head">
          {onBack && (
            <button type="button" className="icon-btn" aria-label="返回菜单" onClick={onBack}>
              <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
                strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><path d="M14.5 6l-6 6 6 6" /></svg>
            </button>
          )}
          <h2 style={{ paddingLeft: onBack ? 0 : 10 }}>{title}</h2>
          <button type="button" className="icon-btn" aria-label="关闭" onClick={onClose}>
            <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
              strokeWidth="1.9" strokeLinecap="round"><path d="M6 6l12 12 M18 6L6 18" /></svg>
          </button>
        </div>
        <div className="sheet-body">{children}</div>
      </div>
    </div>
  );
}
