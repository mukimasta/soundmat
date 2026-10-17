import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { hello, mat, playingState } from '../test/fixtures';
import { setup } from '../test/render';

function connect(client: any, extra: Record<string, unknown> = {}) {
  const st = playingState() as any;
  st.status.recording = { state: 'idle' };
  st.catalog.recordings = [];
  Object.assign(st, extra);
  act(() => { client.handle(hello(st)); client.handle(mat([])); });
}

const patch = (client: any, changes: [string, unknown][]) => act(() => client.handle({ type: 'patch', changes }));

test('record button: start, countdown, slate, recording, stop', async () => {
  const { client, posts, view } = setup();
  connect(client);
  await userEvent.click(screen.getByRole('button', { name: '开始录制' }));
  expect(posts).toContainEqual(['/api/recording/start', undefined]);
  patch(client, [['status.recording', { state: 'countdown', count: 2, elapsed: 1.2 }]]);
  expect(screen.getByRole('button', { name: '正在倒计时' })).toBeDisabled();
  expect(screen.getByText('倒计时 2')).toBeInTheDocument();
  expect(view.container.querySelector('.count-overlay')!.textContent).toBe('2');
  patch(client, [['status.recording', { state: 'recording', flash: true, elapsed: 3.1 }]]);
  expect(view.container.querySelector('.slate-overlay')).not.toBeNull();
  patch(client, [['status.recording', { state: 'recording', flash: false, elapsed: 75 }]]);
  expect(screen.getByText('01:15')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '停止录制' }));
  expect(posts).toContainEqual(['/api/recording/stop', undefined]);
});

test('start failure shows the reason', async () => {
  const { client } = setup();
  client.post = async () => { throw new Error('剩余空间 0.1 GB，不足以录制 10 分钟'); };
  connect(client);
  await userEvent.click(screen.getByRole('button', { name: '开始录制' }));
  expect(screen.getByRole('alert').textContent).toContain('剩余空间 0.1 GB');
});

test('recordings sheet lists and links downloads', async () => {
  const { client } = setup();
  connect(client, { catalog: { ...(playingState() as any).catalog, recordings: [
    { name: '2026-10-17_095759_lofi_1', startedAt: '2026-10-17T09:57:59.782+00:00', title: 'Lo-Fi Loop · Progression 1', duration: 75.2, audio: true },
  ] } });
  await userEvent.click(screen.getByRole('button', { name: '菜单' }));
  const menu = screen.getByRole('dialog', { name: '菜单' });
  expect(within(menu).getByText('1 段')).toBeInTheDocument();
  await userEvent.click(within(menu).getByRole('button', { name: /已录制/ }));
  const sheet = screen.getByRole('dialog', { name: '已录制' });
  expect(within(sheet).getByText('Lo-Fi Loop · Progression 1 · 01:15')).toBeInTheDocument();
  expect(within(sheet).getByRole('link', { name: '下载这段录制' }).getAttribute('href'))
    .toBe('/api/recordings/2026-10-17_095759_lofi_1/download');
});
