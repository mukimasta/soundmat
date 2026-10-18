import { decodeLeds } from './MatView';

test('LED preview hex decodes to colours, dim LEDs count as off', () => {
  const out = decodeLeds('ff00000a0a0a0080ff', 4);
  expect(out).toEqual([[255, 0, 0], null, [0, 128, 255], null]);
  expect(decodeLeds(null, 2)).toEqual([null, null]);
});
