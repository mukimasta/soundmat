import { applyChange, applyChanges, getPath } from './patch';

test('applies dotted paths immutably', () => {
  const a = { status: { current: { virtual: true } } };
  const b = applyChange(a, 'status.current.arrangement', 'kyoto');
  expect(getPath(b, 'status.current.arrangement')).toBe('kyoto');
  expect(getPath(b, 'status.current.virtual')).toBe(true);
  expect(getPath(a, 'status.current.arrangement')).toBeUndefined();
});

test('creates missing branches and replaces non-objects', () => {
  const t = applyChanges({ x: 1 }, [['x.y', 2], ['a.b.c', [1]]]);
  expect(t).toEqual({ x: { y: 2 }, a: { b: { c: [1] } } });
});
