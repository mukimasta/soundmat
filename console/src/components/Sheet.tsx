import type { ReactNode } from 'react';

interface Props {
  title: string;
  onClose: () => void;
  onBack?: () => void;
  children: ReactNode;
}

/** 从底部升起的面板（设计稿的编排、菜单、已录制、设置）。 */
export function Sheet({ title, onClose, onBack, children }: Props) {
  return (
    <div className="sheet-backdrop">
      <button type="button" className="close-area" aria-label="关闭面板" onClick={onClose} />
      <div className="sheet" role="dialog" aria-modal="true" aria-label={title}>
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
