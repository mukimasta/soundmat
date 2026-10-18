import { act, fireEvent, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { LOFI_METERS, hello, mat, playingState } from '../test/fixtures';
import { setup } from '../test/render';

function connect(client: ReturnType<typeof setup>['client']) {
  act(() => {
    client.handle({ ...hello(playingState()), config: [{ label: '占用阈值', value: '500 / 4095' }] });
    client.handle(mat([]));
  });
}

test('mat page shows mode status, ring labels and now-playing card', () => {
  const { client } = setup();
  connect(client);
  expect(screen.getByText('每环一层 · 左右两只音箱')).toBeInTheDocument();
  expect(screen.getByText('输出 — dB')).toBeInTheDocument();
  expect(document.querySelector('.meters')!.textContent).toContain('竹林');
  expect(screen.getByText('Ambient · 氛围 · 演奏中')).toBeInTheDocument();
});

test('arrangement sheet: switch, missing hint; volume on the mat page', async () => {
  const { client, posts } = setup();
  connect(client);
  await userEvent.click(screen.getByRole('button', { name: /当前编排：京都岚山/ }));
  const dialog = screen.getByRole('dialog', { name: '编排' });
  expect(within(dialog).getByText('缺少 2 个声音素材')).toBeInTheDocument();
  expect(within(dialog).getByText('正在演奏')).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole('button', { name: /Lo-Fi Loop/ }));
  expect(posts).toContainEqual(['/api/arrangements/lofi_1/play', undefined]);

  act(() => client.handle({ type: 'patch', changes: [
    ['status.current.arrangement', 'lofi_1'],
    ['status.current.switching', { from: 'kyoto', to: 'lofi_1', progress: 0.37 }],
  ] }));
  expect(within(dialog).getByText('正在交叉淡化 37%')).toBeInTheDocument();
  expect(within(dialog).getByText('正在淡出')).toBeInTheDocument();
  expect(screen.getByText('正在切换到 Lo-Fi Loop · Progression 1 · 37%')).toBeInTheDocument();

  expect(within(dialog).queryByLabelText('总音量')).toBeNull();      // 总音量在主页上，不在编排面板里
  const slider = screen.getByLabelText('总音量');
  await act(async () => {
    fireEvent.change(slider, { target: { value: '79' } });
    await new Promise((r) => setTimeout(r, 200));
  });
  expect(posts).toContainEqual(['/api/settings', { changes: { 'sound.volume': 0.79 } }]);
});

test('menu → settings: layout, orientation, stems, read-only config', async () => {
  const { client, posts } = setup();
  connect(client);
  await userEvent.click(screen.getByRole('button', { name: '菜单' }));
  await userEvent.click(screen.getByRole('button', { name: /设置/ }));
  const dialog = screen.getByRole('dialog', { name: '设置' });
  await userEvent.selectOptions(within(dialog).getByLabelText('音箱布局'), 'quad');
  expect(posts).toContainEqual(['/api/settings', { changes: { 'sound.layout': 'quad' } }]);
  await userEvent.click(within(dialog).getByRole('button', { name: '顺时针 15 度' }));
  expect(posts).toContainEqual(['/api/settings', { changes: { 'sound.orientation': 15 } }]);
  await userEvent.click(within(dialog).getByRole('switch', { name: '录制分轨' }));
  expect(posts).toContainEqual(['/api/settings', { changes: { 'recording.stems': false } }]);
  expect(within(dialog).getByText('500 / 4095')).toBeInTheDocument();
  await userEvent.click(within(dialog).getByRole('button', { name: '返回菜单' }));
  expect(screen.getByRole('dialog', { name: '菜单' })).toBeInTheDocument();
});

test('dashboard shows recent warnings and returns to mat', async () => {
  const { client } = setup();
  connect(client);
  await userEvent.click(screen.getByRole('button', { name: '看板' }));
  expect(screen.getByText(/缺少 2 个声音素材/)).toBeInTheDocument();
  expect(screen.getByText('输入来自点击，不是实体垫子')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '返回垫面' }));
  expect(screen.getByText('点按垫面放下，再点拿起')).toBeInTheDocument();
});

test('jam status line shows section progress and Lo-Fi reading', () => {
  const { client } = setup();
  act(() => {
    client.handle(hello(playingState()));
    client.handle({ type: 'patch', changes: [
      ['status.current.arrangement', 'lofi_1'],
      ['status.current.meters', LOFI_METERS],
      ['status.current.modeStatus', { text: '第 3 段 C · 0:44 / 2:08', reading: 'Lo-Fi 45%', transport: 'playing' }],
    ] });
    client.handle({ type: 'levels', output: [-12, -12], meters: [-20, -9, -120, -120, -120, -14, -120, -120] });
  });
  expect(screen.getByText('第 3 段 C · 0:44 / 2:08')).toBeInTheDocument();
  expect(screen.getByText('Lo-Fi 45%')).toBeInTheDocument();
  expect(screen.getByText('Jam · 合奏 · 120 BPM · 演奏中')).toBeInTheDocument();
  const meters = document.querySelector('.meters')!;
  expect(meters.textContent).toContain('暗电钢');
  expect(meters.textContent).not.toContain('控制');               // 控制环不显示电平条
  // 背景（和声、鼓）与石头触发的层分成两组，名字各只写一次
  const groups = meters.querySelectorAll('.meter-group');
  expect(groups).toHaveLength(2);
  expect(groups[0].textContent).toBe('和声鼓');
  expect(meters.querySelectorAll('.meter')).toHaveLength(8);
  expect(meters.getAttribute('aria-label')).toContain('正在发声：和声、鼓、暗电钢');
  act(() => client.handle({ type: 'patch', changes: [
    ['status.current.modeStatus', { text: '曲终 · 清空中间两环，再压一次重新开始', reading: '', transport: 'ended' }],
  ] }));
  expect(screen.getByText('Jam · 合奏 · 120 BPM · 曲终')).toBeInTheDocument();
});

test('sheets take focus, close on Escape and return focus to the opener', async () => {
  const { client } = setup();
  connect(client);
  const opener = screen.getByRole('button', { name: /当前编排：京都岚山/ });
  await userEvent.click(opener);
  const dialog = screen.getByRole('dialog', { name: '编排' });
  expect(dialog).toHaveFocus();
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(opener).toHaveFocus();
  // 菜单 → 设置 → Esc：焦点回到底部的菜单按钮
  const menu = screen.getByRole('button', { name: '菜单' });
  await userEvent.click(menu);
  await userEvent.click(screen.getByRole('button', { name: /设置/ }));
  expect(screen.getByRole('dialog', { name: '设置' })).toHaveFocus();
  await userEvent.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(menu).toHaveFocus();
});
