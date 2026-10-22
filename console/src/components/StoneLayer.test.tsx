import { render } from '@testing-library/react';
import { MatView } from './MatView';
import { geometry } from '../test/fixtures';
import { stoneHue } from './StoneLayer';

const geo = geometry();
const pressure = new Array(224).fill(0);

function view(stones: { id: number; zone: number; r: number; a: number; s: number }[]) {
  return <MatView geometry={geo} pressure={pressure} occupied={stones.map((s) => s.zone)} stones={stones} ledCount={108} />;
}

function edgeColor(el: Element) {
  return el.querySelector(':scope > g > ellipse')?.getAttribute('stroke');
}

test('a stone keeps its own colour and shape while it moves; different stones differ', () => {
  const { container, rerender } = render(view([{ id: 3, zone: 98, r: 13.32, a: 22.5, s: 3 }]));
  const first = container.querySelector('[data-stone-id="3"]')!;
  const colour = edgeColor(first);
  const shape = first.querySelector('g')!.getAttribute('transform');
  // 挪到隔壁的区，又到下一环：颜色和样子不变
  rerender(view([{ id: 3, zone: 99, r: 13.32, a: 33.75, s: 3 }]));
  rerender(view([{ id: 3, zone: 131, r: 16.43, a: 33.75, s: 3 }]));
  const moved = container.querySelector('[data-stone-id="3"]')!;
  expect(edgeColor(moved)).toBe(colour);
  expect(moved.querySelector('g')!.getAttribute('transform')).toBe(shape);
  rerender(view([{ id: 3, zone: 131, r: 16.43, a: 33.75, s: 3 }, { id: 4, zone: 140, r: 16.43, a: 135, s: 2 }]));
  expect(edgeColor(container.querySelector('[data-stone-id="4"]')!)).not.toBe(colour);
});

test('consecutive stones get far-apart hues', () => {
  for (let id = 1; id < 30; id++) {
    const d = Math.abs(stoneHue(id) - stoneHue(id + 1)) % 360;
    expect(Math.min(d, 360 - d)).toBeGreaterThan(90);
  }
});

test('moving leaves a trail, wobbling in place does not; a new stone ripples', () => {
  const { container, rerender } = render(view([{ id: 7, zone: 98, r: 13.32, a: 22.5, s: 3 }]));
  expect(container.querySelector('[data-drop="7"]')).not.toBeNull();
  expect(container.querySelector('[data-trail="7"]')).toBeNull();
  // 原地抖动（位置只差零点几）：没有轨迹
  rerender(view([{ id: 7, zone: 98, r: 13.4, a: 22.9, s: 3 }]));
  rerender(view([{ id: 7, zone: 98, r: 13.3, a: 22.2, s: 3 }]));
  expect(container.querySelector('[data-trail="7"]')).toBeNull();
  // 挪了两下，每下约 1.2 厘米
  rerender(view([{ id: 7, zone: 99, r: 13.32, a: 28.0, s: 3 }]));
  rerender(view([{ id: 7, zone: 99, r: 13.32, a: 33.0, s: 3 }]));
  expect(container.querySelector('[data-trail="7"]')!.querySelectorAll('line').length).toBe(2);
  // 拿起后轨迹也消失
  rerender(view([]));
  expect(container.querySelector('[data-trail="7"]')).toBeNull();
});

test('without stone ids (older messages) stones are drawn at their zone in ring colour', () => {
  const { container } = render(
    <MatView geometry={geo} pressure={pressure} occupied={[40, 41]} ledCount={108} />,
  );
  const marks = container.querySelectorAll('[data-stone]');
  expect(marks).toHaveLength(2);
  expect(marks[0].getAttribute('data-stone-id')).toBeNull();
});
