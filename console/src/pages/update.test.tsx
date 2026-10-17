import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { hello, mat, playingState } from '../test/fixtures';
import { setup } from '../test/render';

const RELEASES = [
  { tag: 'build-c77c126', commit: 'c77c126', branch: 'master', builtAt: '2026-10-17T16:40:00-07:00', current: false },
  { tag: 'build-b7d0e33', commit: 'b7d0e33', branch: 'stage9', builtAt: '2026-10-17T16:20:00-07:00', current: false },
  { tag: 'build-4b771d7', commit: '4b771d7', branch: 'master', builtAt: '2026-10-17T15:50:00-07:00', current: true },
];

function state() {
  const st = playingState() as any;
  st.status.program = { uptime: 100, restarts: 0, version: { commit: '4b771d7', branch: 'master',
    deployedAt: '2026-10-17T15:50:00-07:00', dirty: null, source: 'deploy' } };
  st.status.update = { enabled: true, state: 'idle', message: '', previous: 'a1b2c3d', failed: null };
  return st;
}

async function open(info: unknown) {
  const env = setup();
  env.client.get = async () => info;
  act(() => { env.client.handle(hello(state())); env.client.handle(mat([])); });
  await userEvent.click(screen.getByRole('button', { name: '菜单' }));
  await userEvent.click(screen.getByRole('button', { name: /软件更新/ }));
  return env;
}

test('update needs a second tap to confirm; other branches are folded', async () => {
  const { posts } = await open({ allowed: true, enabled: true, available: RELEASES, error: null });
  const sheet = screen.getByRole('dialog', { name: '软件更新' });
  expect(within(sheet).getByLabelText('当前版本').textContent).toContain('4b771d7');
  expect(sheet.querySelector('[data-release="build-b7d0e33"]')).toBeNull();          // 其他分支默认折叠
  await userEvent.click(within(sheet).getByRole('button', { name: '显示其他分支（1）' }));
  expect(sheet.querySelector('[data-release="build-b7d0e33"]')).not.toBeNull();
  const row = sheet.querySelector('[data-release="build-c77c126"]') as HTMLElement;
  await userEvent.click(within(row).getByRole('button', { name: '更新' }));
  expect(posts).toEqual([]);                                                          // 第一次只是准备
  await userEvent.click(within(row).getByRole('button', { name: '确认更新' }));
  expect(posts).toEqual([['/api/update', { tag: 'build-c77c126' }]]);
  expect(within(sheet.querySelector('[data-release="build-4b771d7"]') as HTMLElement).getByText('正在运行')).toBeInTheDocument();
  await userEvent.click(within(sheet).getByRole('button', { name: '回到上一版 a1b2c3d' }));
  await userEvent.click(within(sheet).getByRole('button', { name: '确认回到上一版 a1b2c3d' }));
  expect(posts[1]).toEqual(['/api/update/rollback', undefined]);
});

test('people on the hotspot only see the current version', async () => {
  await open({ allowed: false, enabled: true, available: [], error: null });
  const sheet = screen.getByRole('dialog', { name: '软件更新' });
  expect(within(sheet).getByText(/只有从本机或 Tailscale 打开的控制台能更新/)).toBeInTheDocument();
  expect(within(sheet).queryByRole('button', { name: '更新' })).toBeNull();
  expect(within(sheet).queryByRole('button', { name: /回到上一版/ })).toBeNull();
});
