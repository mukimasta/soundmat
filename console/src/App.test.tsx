import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { App } from './App';
import { SoundMatClient } from './api/client';
import { ClientProvider } from './api/context';
import { hello, mat } from './test/fixtures';

function setup() {
  const client = new SoundMatClient('http://test');
  const posts: [string, unknown][] = [];
  client.post = async (path: string, body?: unknown) => {
    posts.push([path, body]);
    return {};
  };
  const view = render(
    <ClientProvider client={client}>
      <App />
    </ClientProvider>,
  );
  return { client, posts, view };
}

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
