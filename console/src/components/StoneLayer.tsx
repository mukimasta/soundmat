import { useRef } from 'react';
import type { StoneMsg, Zone } from '../api/types';
import { RING_COLORS, polar } from './geometry';

/** 挪动的轨迹保留多久（毫秒）、刚放下的涟漪持续多久 */
const TRAIL_MS = 1400;
const DROP_MS = 900;
/**
 * 离上一个轨迹点至少这么远（绘图单位约等于厘米）才记一个新点。静止的石头位置每帧会抖一点
 * （真实游玩里 90% 在 0.2 以内，偶尔接近 1），真正挪动时一帧能走 2–3；挪一两厘米就有轨迹。
 */
const TRAIL_STEP = 1.0;

/**
 * 每颗石头一个固定的颜色：标识按黄金角取色相，相邻编号的石头颜色差得远，同一颗石头从放下到拿起不变。
 * 饱和度、亮度固定，在深色垫面上都看得清，又不和各环的颜色抢。
 */
export function stoneHue(id: number): number {
  return (id * 137.508 + 24) % 360;
}

function stoneColor(id: number, alpha = 1): string {
  return `hsla(${stoneHue(id).toFixed(1)}, 72%, 68%, ${alpha})`;
}

/** 每颗石头固定的样子（扁圆、朝向、高光位置），挪动时不变，看起来是同一颗在滑 */
function pebble(id: number) {
  const h = Math.abs(Math.sin(id * 12.9898) * 43758.5453) % 1;
  const k = Math.abs(Math.sin(id * 78.233) * 12345.678) % 1;
  return { rx: 1.14 + 0.16 * h, ry: 0.86 + 0.12 * k, rot: Math.round((h * 180 + k * 40) % 180) };
}

interface Point { x: number; y: number; t: number }
interface Track { pts: Point[]; born: number }

export interface Located { id: number; zone: Zone; x: number; y: number }

/**
 * 垫面上的石头：每颗有自己的颜色和样子；挪动时身后留一道渐隐的轨迹，刚放下时泛起一圈涟漪。
 * 没有石头标识（旧的消息只有被占用的区）时 id 为负，按环色画、没有轨迹。
 */
export function StoneLayer({ stones }: { stones: Located[] }) {
  const tracks = useRef(new Map<number, Track>());
  const now = typeof performance !== 'undefined' ? performance.now() : Date.now();
  const seen = new Set<number>();
  for (const s of stones) {
    if (s.id < 0) continue;
    seen.add(s.id);
    let tr = tracks.current.get(s.id);
    if (!tr) {
      tr = { pts: [], born: now };
      tracks.current.set(s.id, tr);
    }
    const last = tr.pts[tr.pts.length - 1];
    if (!last || Math.hypot(last.x - s.x, last.y - s.y) >= TRAIL_STEP) tr.pts.push({ x: s.x, y: s.y, t: now });
    while (tr.pts.length > 1 && now - tr.pts[0].t > TRAIL_MS) tr.pts.shift();
  }
  for (const id of [...tracks.current.keys()]) if (!seen.has(id)) tracks.current.delete(id);

  return (
    <g pointerEvents="none">
      {stones.map((s) => {
        const tr = s.id >= 0 ? tracks.current.get(s.id) : undefined;
        // 轨迹画到石头现在的位置，最后一段跟着石头走
        const pts = tr && tr.pts.length >= 2 ? [...tr.pts.slice(0, -1), { x: s.x, y: s.y, t: now }] : [];
        if (pts.length < 2) return null;
        return (
          <g key={`trail-${s.id}`} data-trail={s.id}>
            {pts.slice(1).map((p, i) => {
              const a = pts[i];
              const age = Math.min(1, (now - p.t) / TRAIL_MS);
              const f = 1 - age;
              return (
                <line key={i} x1={a.x} y1={a.y} x2={p.x} y2={p.y} stroke={stoneColor(s.id, 0.55 * f)}
                  strokeWidth={(0.3 + 1.1 * f).toFixed(2)} strokeLinecap="round" />
              );
            })}
          </g>
        );
      })}
      {stones.map((s) => {
        const known = s.id >= 0;
        const ring = RING_COLORS[s.zone.ring];
        const halo = known ? stoneColor(s.id, 0.3) : `rgba(${ring[0]},${ring[1]},${ring[2]},0.38)`;
        const edge = known ? stoneColor(s.id, 0.95) : 'none';
        const shape = known ? pebble(s.id) : { rx: 1.22, ry: 0.94, rot: Math.round((s.zone.center * 1.7 + s.zone.ring * 23) % 180) };
        const fresh = known && now - (tracks.current.get(s.id)?.born ?? -Infinity) < DROP_MS;
        return (
          <g key={known ? s.id : `z${s.zone.index}`} data-stone={s.zone.index} data-stone-id={known ? s.id : undefined}
            transform={`translate(${s.x} ${s.y})`}>
            {fresh && <circle className="stone-drop" data-drop={s.id} r="1.6" fill="none" stroke={stoneColor(s.id, 0.8)} strokeWidth="0.22" />}
            <ellipse rx="2.05" ry="1.75" fill={halo} transform={`rotate(${shape.rot})`} />
            <g transform={`rotate(${shape.rot})`}>
              <ellipse rx={shape.rx} ry={shape.ry} fill="#ECE6DB" stroke={edge} strokeWidth="0.2" />
              <ellipse cx={-0.3 * shape.rx} cy={-0.3 * shape.ry} rx={0.42 * shape.rx} ry={0.28 * shape.ry} fill="#FFFFFF" opacity="0.85" />
            </g>
          </g>
        );
      })}
    </g>
  );
}

/** 石头的位置：有位置时按位置（骑在分界线上的落在线上），否则在主区中心 */
export function locate(geometry: Zone[], stones: StoneMsg[] | undefined, occupied: number[]): Located[] {
  if (stones) {
    return stones.filter((s) => geometry[s.zone]).map((s) => {
      const [x, y] = polar(s.r, s.a);
      return { id: s.id, zone: geometry[s.zone], x, y };
    });
  }
  return occupied.filter((z) => geometry[z]).map((z, i) => {
    const g = geometry[z];
    const [x, y] = polar((g.rInner + g.rOuter) / 2, g.center);
    return { id: -1 - i, zone: g, x, y };
  });
}
