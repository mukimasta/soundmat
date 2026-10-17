import { initialState, reduce } from './client';
import { hello, mat } from '../test/fixtures';

test('hello connects, patch updates, other types go to streams', () => {
  let s = reduce(initialState, hello({ status: { current: { virtual: true } } }));
  expect(s.connected).toBe(true);
  expect(s.geometry).toHaveLength(224);
  s = reduce(s, { type: 'patch', changes: [['status.current.virtual', false]] });
  expect((s.state.status as any).current.virtual).toBe(false);
  s = reduce(s, mat([3]));
  expect(s.mat?.occupied).toEqual([3]);
  s = reduce(s, { type: 'leds', colors: [null] });
  expect(s.streams.leds).toEqual({ colors: [null] });
});
