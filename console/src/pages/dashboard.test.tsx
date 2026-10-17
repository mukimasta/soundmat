import { act, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { hello, mat, playingState } from '../test/fixtures';
import { setup } from '../test/render';

const OK = { level: 'ok', reason: '' };

function state(health: Record<string, unknown>, extra: Record<string, unknown> = {}) {
  const st = playingState() as any;
  st.status.current.virtual = false;
  st.status.health = health;
  st.status.mat = { source: 'controller', connected: true, port: '/dev/ttyUSB0', fps: 58.6, checksumErrors: 0 };
  st.status.matHistory = [58, 59, 58.6];
  st.status.audio = {
    synth: { online: true, synthdefsLoaded: true, sampleRate: 48000, avgLoad: 22, peakLoad: 30 },
    outputDevice: { name: 'USB-Audio - JCALLY JM6', usb: true }, channels: 2,
    buffer: { period: 2048, periods: 2, driver: 'JACK' }, xruns: 0, loadHistory: [20, 22],
    assets: { missing: [], needed: 14 }, engine: { voices: 18, budget: 48 },
  };
  st.status.network = { name: 'iPhone 热点', address: '172.20.10.3', tailscale: 'Running', tailscaleAddress: '100.101.33.8', localName: 'soundmat-pi.local', line: 'iPhone 热点 · soundmat-pi.local' };
  st.status.machine = { host: 'soundmat-pi', model: 'Raspberry Pi 5', tempC: 49, throttled: false, memUsedMB: 800, memTotalMB: 2048,
    diskFreeGB: 52, diskTotalGB: 64, uptime: 9600, programUptime: 9000 };
  Object.assign(st.status, extra);
  return st;
}

test('normal dashboard', async () => {
  const { client } = setup();
  act(() => { client.handle(hello(state({ sound: OK, mat: OK, net: OK, overall: 'ok', issues: [] }))); client.handle(mat([])); });
  expect(screen.queryByRole('button', { name: /看板，有 1 项/ })).not.toBeInTheDocument();
  expect(screen.getByText('iPhone 热点 · soundmat-pi.local')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '看板' }));
  expect(screen.getByText('一切正常')).toBeInTheDocument();
  const sound = screen.getByRole('region', { name: '声音' });
  expect(within(sound).getByText('USB 声卡 · JCALLY JM6')).toBeInTheDocument();
  expect(within(sound).getByText('14 / 14')).toBeInTheDocument();
  expect(within(sound).getByText('✓ 最近 1 小时没有卡顿')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: '垫子' })).getByText('58.6')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: '网络' })).getByText('已连接 · 100.101.33.8')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: '网络' })).getByText('soundmat-pi.local · 172.20.10.3')).toBeInTheDocument();
  expect(within(screen.getByRole('region', { name: '机器' })).getByText('Raspberry Pi 5')).toBeInTheDocument();
});

test('error: alert on mat page, nav dot label, dashboard reason, test tone', async () => {
  const { client, posts } = setup();
  const reason = '合成器服务没有使用 USB 声卡，当前输出到 vc4-hdmi，音箱不会发声';
  act(() => {
    client.handle(hello(state(
      { sound: { level: 'error', reason }, mat: OK, net: OK, overall: 'error', issues: [`声音：${reason}`] },
    )));
    client.handle({ type: 'patch', changes: [['status.audio.outputDevice', { name: 'vc4-hdmi', usb: false }]] });
  });
  expect(screen.getByText(`声音：${reason}`)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '看板，有 1 项需要处理' }));
  expect(screen.getByText('异常', { selector: '.head' })).toBeInTheDocument();
  expect(screen.getByText('期望 USB 声卡，音箱不会发声')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: '右声道测试音' }));
  expect(posts).toContainEqual(['/api/audio/test-tone', { channel: 1 }]);
  expect(screen.getByText('右 · 发声')).toBeInTheDocument();
});

test('disconnected dashboard hides stale data', async () => {
  const { client } = setup();
  act(() => client.handle(hello(state({ sound: OK, mat: OK, net: OK, overall: 'ok', issues: [] }))));
  await userEvent.click(screen.getByRole('button', { name: '看板' }));
  act(() => (client as any).set({ ...client.getState(), connected: false, mat: null, streams: {} }));
  expect(screen.getByText('已断开', { selector: '.head' })).toBeInTheDocument();
  expect(screen.queryByRole('region', { name: '声音' })).not.toBeInTheDocument();
});

test('rhythm card, network kind, program and recording time', async () => {
  const { client } = setup();
  const extra = {
    rates: {
      sensing: { actual: 58.6, expected: null }, perception: { actual: 58.6, expected: null },
      beat: { actual: 60, expected: 60 }, light: { actual: 41, expected: 60 },
      ledWrites: { actual: 41, expected: 60 }, pushMat: { actual: 12, expected: 30 }, pushLeds: { actual: 0, expected: 60 },
    },
    timing: { overruns: 7, overrunsRecent: 2, late: 0, lateRecent: 0, yields: 3, rejected: 0, overrunsAttention: false, lateAttention: false },
    program: { uptime: 5400, restarts: 1, version: { commit: '2d09273', deployedAt: '2026-10-17T15:04:00-07:00', dirty: null, source: 'deploy' } },
    storage: { freeGB: 52, minutes: 1500 },
  };
  const st = state({ sound: OK, mat: OK, net: OK, overall: 'ok', issues: [] }, extra);
  st.status.network = { ...st.status.network, name: 'soundmat-ap', kind: 'selfHotspot', apClients: 2 };
  act(() => { client.handle(hello(st)); client.handle(mat([])); });
  await userEvent.click(screen.getByRole('button', { name: '看板' }));

  const rhythm = screen.getByRole('region', { name: '节奏' });
  const row = (key: string) => rhythm.querySelector(`[data-rate="${key}"]`)!;
  expect(row('beat').textContent).toBe('声音化节拍6060');
  expect(row('light').querySelector('.num')!.getAttribute('style')).toContain('amber');   // 低于期望：标出来
  expect(row('pushLeds').textContent).toContain('最多 60');
  expect(row('pushLeds').querySelector('.num')!.getAttribute('style')).toBeNull();     // 只在有变化时推送：0 不算异常
  expect(row('sensing').textContent).toContain('—');
  expect(row('display')).toBeTruthy();
  expect(within(rhythm).getByText('启动以来 7 次')).toBeInTheDocument();

  const net = screen.getByRole('region', { name: '网络' });
  expect(within(net).getByText('自建热点')).toBeInTheDocument();
  expect(within(net).getByText('约 2 台')).toBeInTheDocument();

  const machine = screen.getByRole('region', { name: '机器' });
  expect(within(machine).getByText('1 小时 30 分')).toBeInTheDocument();
  expect(within(machine).getByText('1 次')).toBeInTheDocument();
  expect(within(machine).getByText('2d09273 · 部署于 2026-10-17 15:04')).toBeInTheDocument();
  expect(within(machine).getByText('约 25 小时')).toBeInTheDocument();
});
