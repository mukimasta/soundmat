export function VirtualBanner({ hint }: { hint: string }) {
  return (
    <div role="status" className="banner banner-virtual">
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
        strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
        <path d="M6 4l12 6.4-5.2 1.6-1.6 5.2z M13.4 13.4l4.6 4.6" />
      </svg>
      <strong>虚拟垫子</strong>
      <span>{hint}</span>
    </div>
  );
}

export function DisconnectedBanner() {
  return (
    <div role="status" className="banner banner-off">
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor"
        strokeWidth="1.9" strokeLinecap="round">
        <path d="M20 12a8 8 0 1 1-8-8" />
      </svg>
      <strong>已断开</strong>
      <span>正在重新连接，不显示过时的数据</span>
    </div>
  );
}
