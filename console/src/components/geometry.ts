/** 垫面绘图：坐标单位与主机程序的区域几何一致（环中心半径约 4–25.75），12 点方向为 0°，顺时针。 */
export const LED_RADIUS = 29.15;

/** 每环的代表色（与第一版 Jam 灯光、设计稿一致） */
export const RING_COLORS: [number, number, number][] = [
  [100, 108, 128], [148, 112, 88], [88, 72, 210], [32, 188, 148],
  [48, 152, 255], [200, 72, 168], [218, 158, 48], [255, 108, 32],
];

const r3 = (v: number) => Math.round(v * 1000) / 1000;

export function polar(r: number, deg: number): [number, number] {
  const a = (deg * Math.PI) / 180;
  return [r3(r * Math.sin(a)), r3(-r * Math.cos(a))];
}

/** 一个环形扇区的路径；相邻区域之间留 0.35 的缝 */
export function sectorPath(ri: number, ro: number, centerDeg: number, spanDeg: number): string {
  const rc = (ri + ro) / 2;
  const half = ((0.175 / rc) * 180) / Math.PI;
  const a0 = centerDeg - spanDeg / 2 + half;
  const a1 = centerDeg + spanDeg / 2 - half;
  const [x0, y0] = polar(ro, a0);
  const [x1, y1] = polar(ro, a1);
  const [x2, y2] = polar(ri, a1);
  const [x3, y3] = polar(ri, a0);
  return `M${x0} ${y0} A${ro} ${ro} 0 0 1 ${x1} ${y1} L${x2} ${y2} A${ri} ${ri} 0 0 0 ${x3} ${y3} Z`;
}

const BASE: [number, number, number] = [27, 26, 23];

/** 压力（0–1）→ 区域填充色：从底色向环色过渡 */
export function zoneFill(p: number, ring: number): string {
  if (!p || p <= 0) return `rgb(${BASE.join(',')})`;
  const c = RING_COLORS[ring % RING_COLORS.length];
  const t = Math.min(1, Math.pow(p, 0.8)) * 0.9;
  const mix = (i: number) => Math.round(BASE[i] + (c[i] - BASE[i]) * t);
  return `rgb(${mix(0)},${mix(1)},${mix(2)})`;
}
