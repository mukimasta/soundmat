import { act, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { setup } from './test/render';
import { hello, mat } from './test/fixtures';

test('shows disconnected state before hello and no mat data', () => {
  setup();
  expect(screen.getByText('已断开')).toBeInTheDocument();
  expect(screen.getByText('已断开 · 暂不显示垫面')).toBeInTheDocument();
  expect(screen.getByRole('img', { name: '垫面：没有数据' })).toBeInTheDocument();
});

test('virtual mat: banner, tap toggles a zone, clear button', async () => {
  const { client, posts, view } = setup();
  act(() => {
    client.handle(hello({ status: { current: { virtual: true } } }));
    client.handle(mat([40]));
  });
  expect(screen.getByText('虚拟垫子')).toBeInTheDocument();
  expect(view.container.querySelectorAll('[data-stone]')).toHaveLength(1);
  const zone = view.container.querySelector('[data-zone="50"]')!;
  await userEvent.click(zone);
  expect(posts).toContainEqual(['/api/virtual/toggle', { zone: 50 }]);
  await userEvent.click(screen.getByRole('button', { name: '清空' }));
  expect(posts).toContainEqual(['/api/virtual/clear', undefined]);
});

test('real controller: zones not tappable, stone count shown', async () => {
  const { client, posts, view } = setup();
  act(() => {
    client.handle(hello({ status: { current: { virtual: false }, mat: { fps: 58.64 } } }));
    client.handle(mat([1, 2], 'controller'));
  });
  expect(screen.queryByText('虚拟垫子')).not.toBeInTheDocument();
  expect(screen.getByText('2 颗石头')).toBeInTheDocument();
  expect(screen.getByText('58.6 fps')).toBeInTheDocument();
  await userEvent.click(view.container.querySelector('[data-zone="50"]')!);
  expect(posts).toHaveLength(0);
});

test('stones are drawn where they are, one mark per stone even when it covers two zones', () => {
  const { client, view } = setup();
  const m = mat([66, 67], 'controller');
  // 一颗石头骑在第 3 环第 2、3 区之间（22.5° 和 33.75° 中间）
  m.occupied = [67];
  m.stones = [{ id: 7, zone: 67, r: 13.32, a: 28.1, s: 3.2 }];
  act(() => {
    client.handle(hello({ status: { current: { virtual: false } } }));
    client.handle(m);
  });
  const marks = view.container.querySelectorAll('[data-stone]');
  expect(marks).toHaveLength(1);
  const a = (28.1 * Math.PI) / 180;
  const want = `translate(${Math.round(13.32 * Math.sin(a) * 1000) / 1000} ${Math.round(-13.32 * Math.cos(a) * 1000) / 1000})`;
  expect(marks[0].getAttribute('transform')).toContain(want);
  expect(screen.getByText('1 颗石头')).toBeInTheDocument();
});
