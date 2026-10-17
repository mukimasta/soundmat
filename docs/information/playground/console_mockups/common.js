/* SoundMat 控制台视觉稿 — 三个方向共用的脚本：双语文案、预览工具条、垫面与灯环渲染、模拟的 Jam 运行。
   这是设计研究用的静态稿，不是产品代码。页面在加载本文件之前定义 window.MAT_THEME。 */
(() => {
  'use strict';

  // ── 垫面几何：8 环，内两环 16 区、外六环 32 区；0° 在 12 点，顺时针 ──
  const RINGS = 8, R_IN = 17, R_OUT = 82, RW = (R_OUT - R_IN) / RINGS;
  const LEDS = 108, R_LED = 91;
  const slices = r => (r < 2 ? 16 : 32);
  const RING_RGB = [[100,108,128],[148,112,88],[88,72,210],[32,188,148],[48,152,255],[200,72,168],[218,158,48],[255,108,32]];
  const CARDINAL = { 0: [255,48,48], 27: [255,140,140], 54: [255,140,140], 81: [255,140,140] };
  const TRAIL = [1, .75, .4, .3, .22, .15, .1, .06, .03, .01];
  const HIT = [[1, .82], [0, 1], [-1, .82], [-2, .52]];
  const LOOP = 4, BARS = 64;   // 120 bpm：扫描一圈 = 2 小节 = 4 秒；曲式 8 遍 × 8 小节
  const FORM = ['A','B','C','C','A','D','D','A'];
  const CHORDS = ['2m9','513','1maj9','69'];

  const DIRS = [
    { f: 'a-paper.html', zh: 'A 纸本', en: 'A Paper' },
    { f: 'b-instrument.html', zh: 'B 仪器', en: 'B Instrument' },
    { f: 'c-soft.html', zh: 'C 柔光', en: 'C Soft' },
  ];

  const I18N = {
    zh: {
      brandSub: '音乐艺术装置', sound: '声音', mat: '垫子', network: '网络', ok: '正常', virtual: '虚拟垫子',
      virtualTitle: '虚拟垫子', virtualHint: '点击区域放下石头，再点一次拿起。中心两环是控制区。',
      clear: '清空', controlPressure: '控制区压力', nowPlaying: '正在演奏', arrangements: '编排',
      record: '录制', stop: '停止', settings: '设置', matTab: '垫面', volume: '音量', chord: '和弦', bar: '小节',
      form: '曲式', lofi: 'Lo-Fi', tempo: '速度', idle: '等待开始', playing: '演奏中', health: '运行状况',
      synth: '合成器服务', output: '输出设备', buffer: '缓冲', xruns: '卡顿', dsp: '运算负载', voices: '声部',
      controller: '控制器', fps: '传感帧率', checksum: '校验错误', machine: '机器', temp: '温度', memory: '内存',
      disk: '剩余空间', uptime: '已运行', address: '地址', events: '事件', placed: '放下', lifted: '拿起',
      arrKyoto: '京都岚山', arrKyotoEn: 'Kyoto Arashiyama', arrKyotoDesc: '寺院、竹林与雨。放下石头，一个场景慢慢展开。',
      arrLofi: 'Lo-Fi 第一首', arrLofiEn: 'Lo-Fi No. 1', arrLofiDesc: '旋转扫描的循环曲，中心两环开始演奏并调节 Lo-Fi。',
      ambient: '氛围', jam: '合奏', active: '当前', input: '输入', stones: '石头', testTone: '声道测试',
      left: '左', right: '右', key: 'C 大调', fig: '图 1　垫面与灯环', legend: '环', running: '运行中',
      roleSub: '低音', rolePluck: '贝斯', rolePad: '拨弦铺底', roleRhodes: '电钢', roleMarimba: '马林巴',
      elapsed: '已演奏', allOk: '一切正常', dashboard: '看板', recent: '最近录制', section: '段落',
      emptyEvents: '还没有事件。点一下垫面试试。', liveMat: '实时垫面', pressure: '压力', countdown: '倒计时',
      recording: '录制中', spaceLeft: '可录约 9 小时', master: '总音量', machineName: 'Raspberry Pi 5',
      now: '当前', level: '输出电平', budget: '声部预算', assets: '音色与素材', loadedAll: '全部加载',
      sampleRate: '采样率', channels: '声道', expected: '与期望一致', throttle: '降频', none: '无', signal: '信号',
      warnings: '最近的警告和错误', w1: '控制器断开，3 秒后自动重连', w2: '声部超出预算，让位 2 次', w3: '合成器服务启动完成',
      noWarnings: '没有警告。', notRecording: '未在录制', mockMatNote: '虚拟垫子不经过控制器，没有传感帧率。',
      fpsHistory: '最近 60 秒', online: '在线', lastMinute: '最近 1 分钟', peak: '峰值', cpu: 'CPU',
    },
    en: {
      brandSub: 'Music art installation', sound: 'Sound', mat: 'Mat', network: 'Network', ok: 'OK', virtual: 'Virtual mat',
      virtualTitle: 'Virtual mat', virtualHint: 'Click a zone to place a stone, click again to lift it. The two center rings are the control zone.',
      clear: 'Clear', controlPressure: 'Control pressure', nowPlaying: 'Now playing', arrangements: 'Arrangements',
      record: 'Record', stop: 'Stop', settings: 'Settings', matTab: 'Mat', volume: 'Volume', chord: 'Chord', bar: 'Bar',
      form: 'Form', lofi: 'Lo-Fi', tempo: 'Tempo', idle: 'Waiting to start', playing: 'Playing', health: 'Health',
      synth: 'Synth server', output: 'Output device', buffer: 'Buffer', xruns: 'Dropouts', dsp: 'DSP load', voices: 'Voices',
      controller: 'Controller', fps: 'Sensor rate', checksum: 'Checksum errors', machine: 'Machine', temp: 'Temperature', memory: 'Memory',
      disk: 'Free space', uptime: 'Uptime', address: 'Address', events: 'Events', placed: 'Placed', lifted: 'Lifted',
      arrKyoto: 'Kyoto Arashiyama', arrKyotoEn: '京都岚山', arrKyotoDesc: 'Temple, bamboo and rain. Each stone unfolds more of the scene.',
      arrLofi: 'Lo-Fi No. 1', arrLofiEn: 'Lo-Fi 第一首', arrLofiDesc: 'A rotating-scan loop. The center rings start it and shape the Lo-Fi.',
      ambient: 'Ambient', jam: 'Jam', active: 'Active', input: 'Input', stones: 'Stones', testTone: 'Channel test',
      left: 'L', right: 'R', key: 'C major', fig: 'Fig. 1　The mat and light ring', legend: 'Rings', running: 'Running',
      roleSub: 'Sub bass', rolePluck: 'Pluck bass', rolePad: 'Pad pluck', roleRhodes: 'Rhodes', roleMarimba: 'Marimba',
      elapsed: 'Elapsed', allOk: 'All systems normal', dashboard: 'Dashboard', recent: 'Recent recordings', section: 'Section',
      emptyEvents: 'No events yet. Try clicking the mat.', liveMat: 'Live mat', pressure: 'Pressure', countdown: 'Countdown',
      recording: 'Recording', spaceLeft: 'About 9 h of space', master: 'Master', machineName: 'Raspberry Pi 5',
      now: 'Now', level: 'Output level', budget: 'Voice budget', assets: 'Instruments & samples', loadedAll: 'All loaded',
      sampleRate: 'Sample rate', channels: 'Channels', expected: 'Matches expected', throttle: 'Throttling', none: 'None', signal: 'Signal',
      warnings: 'Recent warnings and errors', w1: 'Controller disconnected, reconnected after 3 s', w2: 'Voice budget exceeded, 2 voices stolen', w3: 'Synth server started',
      noWarnings: 'No warnings.', notRecording: 'Not recording', mockMatNote: 'The virtual mat bypasses the controller, so there is no sensor rate.',
      fpsHistory: 'Last 60 s', online: 'Online', lastMinute: 'Last minute', peak: 'Peak', cpu: 'CPU',
    },
  };

  // 实机与虚拟垫子下不同的状态值
  const VALUES = {
    real: {
      matStatus: { zh: '已连接 · 62 fps', en: 'Connected · 62 fps' },
      netStatus: { zh: '手机热点', en: 'Phone hotspot' },
      synthV: { zh: '运行中', en: 'Running' },
      outputV: 'USB Audio CODEC · 48 kHz · 2 ch', bufferV: 'JACK 1024 × 2', xrunsV: '0', dspV: '23%',
      controllerV: { zh: '已连接 · ttyACM0', en: 'Connected · ttyACM0' }, fpsV: '62.4 fps', checksumV: '0',
      machineV: 'Raspberry Pi 5', tempV: '51 °C', memV: '0.6 / 8 GB', diskV: '41 GB',
      uptimeV: { zh: '3 小时 12 分', en: '3 h 12 min' },
      netV: { zh: 'iPhone 热点', en: 'iPhone hotspot' }, addrV: 'soundmat.local · 172.20.10.4', tsV: 'soundmat · 100.84.12.7',
      inputV: { zh: '压力垫控制器', en: 'Pressure mat controller' },
      soundLine: { zh: 'USB 声卡 · 48 kHz · 2 声道', en: 'USB audio · 48 kHz · 2 ch' },
      matLine: { zh: '已连接 · 62 fps', en: 'Connected · 62 fps' },
      netLine: { zh: 'iPhone 热点 · Tailscale 在线', en: 'iPhone hotspot · Tailscale online' },
      deviceV: 'USB Audio CODEC', assetsV: '14 / 14',
    },
    mock: {
      matStatus: { zh: '虚拟垫子', en: 'Virtual mat' },
      netStatus: 'localhost',
      synthV: { zh: '运行中', en: 'Running' },
      outputV: 'MacBook Pro Speakers · 48 kHz · 2 ch', bufferV: 'CoreAudio 512', xrunsV: '0', dspV: '9%',
      controllerV: { zh: '未使用', en: 'Not used' }, fpsV: '—', checksumV: '—',
      machineV: { zh: '开发机 · macOS', en: 'Dev machine · macOS' }, tempV: '—', memV: '—', diskV: '—', uptimeV: '—',
      netV: { zh: '本机', en: 'This machine' }, addrV: 'localhost:8000', tsV: '—',
      inputV: { zh: '虚拟垫子（浏览器）', en: 'Virtual mat (browser)' },
      soundLine: { zh: 'MacBook Pro 扬声器 · 48 kHz', en: 'MacBook Pro speakers · 48 kHz' },
      matLine: { zh: '虚拟垫子 · 浏览器输入', en: 'Virtual mat · browser input' },
      netLine: { zh: '本机 · localhost:8000', en: 'This machine · localhost:8000' },
      deviceV: 'MacBook Pro Speakers', assetsV: '14 / 14',
    },
  };

  // ── 状态 ──
  const q = new URLSearchParams(location.search);
  const S = {
    mode: q.get('mode') || 'mock', lang: q.get('lang') || 'zh', view: q.get('view') || 'desktop', page: q.get('page') || 'mat',
    stones: new Set(['0:3','0:9','2:4','3:12','3:20','4:6','4:25','5:14','5:28','6:9','7:2','7:17','7:22']),
    ctrlExtra: 0, t: 26, prevAngle: 0, hits: [], events: [], rec: null, playing: false,
  };
  const T0 = performance.now() / 1000;
  const th = window.MAT_THEME || {};
  const tr = k => I18N[S.lang][k] ?? k;
  const other = () => (S.lang === 'zh' ? 'en' : 'zh');
  const pick = v => (v && typeof v === 'object' ? v[S.lang] : v);
  const mmss = s => `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const hash = k => [...k].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  const f3 = n => +n.toFixed(3);
  const pt = (r, deg) => { const a = (deg - 90) * Math.PI / 180; return [f3(r * Math.cos(a)), f3(r * Math.sin(a))]; };
  const arc = (r1, r2, a1, a2) => {
    const [x1, y1] = pt(r2, a1), [x2, y2] = pt(r2, a2), [x3, y3] = pt(r1, a2), [x4, y4] = pt(r1, a1);
    return `M${x1} ${y1}A${r2} ${r2} 0 0 1 ${x2} ${y2}L${x3} ${y3}A${r1} ${r1} 0 0 0 ${x4} ${y4}Z`;
  };
  // 内两环的区域跨两个外环扇区，并且与外环交错半个扇区：第 s 区以外环第 2s 扇区为中心（见传感器图案 fabric_slices.svg）
  const zoneStart = (r, s) => (r < 2 ? (2 * s - .5) * 11.25 : s * 11.25);
  const zc = k => { const [r, s] = k.split(':').map(Number); const span = 360 / slices(r); return { r, s, span, a: zoneStart(r, s) + span / 2, rad: R_IN + (r + .5) * RW }; };
  const ledAt = deg => ((Math.round(deg / 360 * LEDS) % LEDS) + LEDS) % LEDS;
  const mix = (a, b, t) => `rgb(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(',')})`;

  // ── 文案与模式 ──
  function apply() {
    document.documentElement.lang = S.lang === 'zh' ? 'zh-CN' : 'en';
    document.body.classList.toggle('mode-real', S.mode === 'real');
    document.body.classList.toggle('mode-mock', S.mode === 'mock');
    document.body.classList.toggle('view-phone', S.view === 'phone');
    document.body.classList.toggle('lang-en', S.lang === 'en');
    document.querySelectorAll('[data-t]').forEach(el => { el.textContent = tr(el.dataset.t); });
    document.querySelectorAll('[data-t2]').forEach(el => { el.textContent = I18N[other()][el.dataset.t2] ?? ''; });
    document.querySelectorAll('[data-v]').forEach(el => { el.textContent = pick(VALUES[S.mode][el.dataset.v]) ?? '—'; });
    document.querySelectorAll('[data-lang-btn]').forEach(el => el.classList.toggle('on', el.dataset.langBtn === S.lang));
    document.body.dataset.page = S.page;
    document.querySelectorAll('[data-act="nav"]').forEach(el => el.classList.toggle('on', el.dataset.page === S.page));
    history.replaceState(null, '', `?mode=${S.mode}&lang=${S.lang}&view=${S.view}&page=${S.page}`);
    if (stonesG) stonesChanged();
    renderEvents();
    toolbar();
  }

  // ── 预览工具条（不属于设计本身） ──
  const bar = document.createElement('div');
  bar.className = 'pv-bar';
  document.body.appendChild(bar);
  function toolbar() {
    const cur = location.pathname.split('/').pop();
    const link = f => `${f}?mode=${S.mode}&lang=${S.lang}&view=${S.view}&page=${S.page}`;
    const seg = (key, opts) => `<div class="pv-g">${opts.map(([v, l]) => `<button class="${S[key] === v ? 'on' : ''}" data-pv="${key}" data-val="${v}">${l}</button>`).join('')}</div>`;
    bar.innerHTML =
      `<div class="pv-g">${DIRS.map(d => `<a class="${d.f === cur ? 'on' : ''}" href="${link(d.f)}">${d[S.lang]}</a>`).join('')}</div>` +
      seg('mode', [['real', '实机 Real'], ['mock', 'Mock']]) +
      seg('lang', [['zh', '中'], ['en', 'EN']]) +
      seg('view', [['desktop', '桌面 Desktop'], ['phone', '手机 Phone']]);
  }
  bar.addEventListener('click', e => {
    const b = e.target.closest('[data-pv]');
    if (!b) return;
    S[b.dataset.pv] = b.dataset.val;
    apply();
  });

  const css = document.createElement('style');
  css.textContent = `
    .mode-real .only-mock, .mode-mock .only-real { display: none !important; }
    .app { container: app / inline-size; }
    .stage { min-height: 100vh; }
    body.view-phone .stage { display: flex; justify-content: center; align-items: flex-start; padding: 28px 16px 110px; }
    body.view-phone .app { width: 390px; height: 844px; overflow-y: auto; border-radius: 46px; flex: none;
      box-shadow: 0 0 0 9px #16161a, 0 0 0 10px #2c2c31, 0 40px 90px -20px rgba(0,0,0,.35); scrollbar-width: none; }
    body.view-phone .app::-webkit-scrollbar { display: none; }
    .pv-bar { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%); z-index: 100; display: flex; gap: 6px;
      padding: 6px; border-radius: 14px; background: rgba(22,22,26,.86); backdrop-filter: blur(10px);
      font: 500 12px/1 -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; box-shadow: 0 10px 30px rgba(0,0,0,.25);
      max-width: calc(100vw - 24px); overflow-x: auto; }
    .pv-g { display: flex; gap: 2px; padding-right: 6px; border-right: 1px solid rgba(255,255,255,.12); }
    .pv-g:last-child { border-right: 0; padding-right: 0; }
    .pv-bar a, .pv-bar button { all: unset; cursor: pointer; white-space: nowrap; color: rgba(255,255,255,.62); padding: 7px 10px; border-radius: 9px; }
    .pv-bar a:hover, .pv-bar button:hover { color: #fff; }
    .pv-bar .on { background: rgba(255,255,255,.14); color: #fff; }
    .mat svg { display: block; width: 100%; height: 100%; overflow: visible; user-select: none; -webkit-user-select: none; }
    .mode-mock .zone { cursor: pointer; }
    .mode-mock .zone:hover { fill: ${th.hover || 'rgba(0,0,0,.06)'}; }
  `;
  document.head.appendChild(css);

  // ── 垫面 ──
  const matEl = document.querySelector('[data-mat]');
  const Z = {}, L = [], H = [];
  let stonesG;
  function buildMat() {
    let zones = '', leds = '', halos = '', labels = '';
    for (let r = 0; r < RINGS; r++) {
      const n = slices(r), span = 360 / n, r1 = R_IN + r * RW, r2 = r1 + RW;
      for (let s = 0; s < n; s++) zones += `<path class="zone" data-k="${r}:${s}" d="${arc(r1, r2, zoneStart(r, s), zoneStart(r, s) + span)}"/>`;
      if (th.labels) { const [x, y] = pt(r1 + RW / 2, -2.2); labels += `<text x="${x}" y="${y}">${r}</text>`; }
    }
    for (let i = 0; i < LEDS; i++) {
      const [x, y] = pt(R_LED, i / LEDS * 360);
      halos += `<circle cx="${x}" cy="${y}" r="${th.haloR || 3.4}"/>`;
      leds += `<circle cx="${x}" cy="${y}" r="${th.ledR || 1.4}"/>`;
    }
    const p = th.pebble || ['#9a958c', '#5c5850', '#34312c'];
    matEl.innerHTML = `<svg viewBox="-100 -100 200 200" aria-label="SoundMat">
      <defs>
        <radialGradient id="pebble" cx="34%" cy="28%" r="80%"><stop offset="0" stop-color="${p[0]}"/><stop offset=".55" stop-color="${p[1]}"/><stop offset="1" stop-color="${p[2]}"/></radialGradient>
        <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="${th.glowBlur || 2}"/></filter>
        <filter id="soft" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation=".7"/></filter>
        ${th.defs || ''}
      </defs>
      <g>${th.base ? th.base(R_OUT, R_LED, R_IN) : `<circle r="${R_OUT + 1}" fill="${th.felt || '#eee'}"/>`}</g>
      <g class="m-zones" fill="transparent" stroke="${th.line}" stroke-width="${th.lineW || .3}">${zones}</g>
      <circle r="${R_IN}" fill="${th.hub || 'transparent'}" stroke="${th.line}" stroke-width="${th.lineW || .3}" pointer-events="none"/>
      ${th.hubDeco ? th.hubDeco(R_IN) : ''}
      <g class="m-labels" fill="${th.labelColor || '#999'}" font-size="2.6" text-anchor="middle" dominant-baseline="middle" pointer-events="none" style="font-family:${th.labelFont || 'inherit'}">${labels}</g>
      <g class="m-stones" pointer-events="none"></g>
      <g class="m-halos" filter="url(#glow)" pointer-events="none">${halos}</g>
      <g class="m-leds" pointer-events="none">${leds}</g>
      ${th.over ? th.over(R_OUT, R_LED) : ''}
    </svg>`;
    matEl.querySelectorAll('.zone').forEach(z => { Z[z.dataset.k] = z; });
    matEl.querySelectorAll('.m-leds circle').forEach(c => L.push(c));
    matEl.querySelectorAll('.m-halos circle').forEach(c => H.push(c));
    stonesG = matEl.querySelector('.m-stones');
    matEl.addEventListener('click', e => {
      const z = e.target.closest('.zone');
      if (!z || S.mode !== 'mock') return;
      toggleStone(z.dataset.k);
    });
  }

  let heatMap = {};
  function stonesChanged() {
    let html = '';
    if (S.mode === 'mock' || th.stonesInReal) {
      for (const k of S.stones) {
        const c = zc(k), [x, y] = pt(c.rad, c.a), h = hash(k);
        const rot = h % 180, rx = (th.stoneR || 3.6) * (1 + (h % 7) / 30), ry = rx * (.74 + (h % 5) / 40);
        if (th.stone === 'mark') {
          html += `<circle cx="${x}" cy="${y}" r="${th.stoneR || 1}" fill="${th.stoneFill || '#fff'}"/>`;
        } else if (th.stone === 'dot') {
          html += `<circle cx="${x}" cy="${y}" r="${th.stoneR || 2.4}" fill="${th.stoneFill || '#111'}"/>`;
        } else {
          html += `<g transform="translate(${x} ${y}) rotate(${rot})">
            <ellipse cx=".6" cy="1.1" rx="${rx}" ry="${ry}" fill="rgba(0,0,0,${th.shadowA ?? .22})" filter="url(#soft)"/>
            <ellipse rx="${rx}" ry="${ry}" fill="url(#pebble)"/>
            <ellipse cx="${-rx * .3}" cy="${-ry * .35}" rx="${rx * .35}" ry="${ry * .22}" fill="rgba(255,255,255,.16)"/></g>`;
        }
      }
    }
    stonesG.innerHTML = html;
    // 实机的压力分布：石头所在区域压力高，相邻区域有少量串扰
    heatMap = {};
    for (const k of S.stones) {
      const c = zc(k);
      const w = th.tiles ? .55 + (hash(k) % 40) / 100 : 1;   // 实机里每颗石头重量不同，压力也不同
      heatMap[k] = Math.max(heatMap[k] || 0, w);
      for (const k2 in Z) {
        if (k2 === k) continue;
        const d = zc(k2);
        if (Math.abs(d.r - c.r) > 1) continue;
        let da = Math.abs(d.a - c.a); da = Math.min(da, 360 - da);
        if (da < (c.span + d.span) / 2 + .1) heatMap[k2] = Math.max(heatMap[k2] || 0, (th.tiles ? w * (d.r === c.r ? .16 : .09) : (d.r === c.r ? .22 : .14)));
      }
    }
  }

  function toggleStone(k) {
    const placed = !S.stones.has(k);
    placed ? S.stones.add(k) : S.stones.delete(k);
    S.events.unshift({ placed, k, t: performance.now() / 1000 - T0 });
    S.events.length = Math.min(S.events.length, 40);
    stonesChanged();
    renderEvents();
  }

  function renderEvents() {
    const list = document.querySelector('[data-live="events"]');
    if (!list) return;
    if (!S.events.length) { list.innerHTML = `<li class="ev-empty">${tr('emptyEvents')}</li>`; return; }
    list.innerHTML = S.events.slice(0, 7).map(e => {
      const [r, s] = e.k.split(':');
      return `<li class="${e.placed ? 'ev-in' : 'ev-out'}"><span class="ev-t">${mmss(e.t)}.${Math.floor((e.t % 1) * 10)}</span><span class="ev-a">${tr(e.placed ? 'placed' : 'lifted')}</span><span class="ev-z">R${r} · ${s}</span></li>`;
    }).join('');
  }

  // ── 模拟的 Jam 运行 ──
  const ctrlPressure = () => {
    let n = 0;
    for (const k of S.stones) if (+k[0] < 2) n++;
    return Math.min(1, n * .3 + S.ctrlExtra);
  };

  function step(dt, now) {
    const ctrl = ctrlPressure();
    S.playing = ctrl > .04;
    const prev = S.prevAngle;
    if (S.playing) S.t = (S.t + dt) % (BARS * 2);
    const ang = ((S.t % LOOP) / LOOP) * 360;
    if (S.playing) {
      const crossed = c => (ang >= prev ? c > prev && c <= ang : c > prev || c <= ang);
      for (const k of S.stones) {
        const c = zc(k);
        if (c.r < 2) continue;
        if (crossed(c.a)) S.hits.push({ i: ledAt(c.a), rgb: RING_RGB[c.r], t0: now });
      }
    }
    S.hits = S.hits.filter(h => now - h.t0 < .2);
    S.prevAngle = ang;
    return { ctrl, ang };
  }

  function ledFrame(now, ang) {
    const white = th.white || [255, 255, 255], off = th.ledOff || [220, 220, 220];
    const breath = Math.sin(now * 1.35) * .5 + .5;
    const head = ledAt(ang);
    const marks = {};
    if (S.playing) for (const k of S.stones) {
      const c = zc(k);
      if (c.r < 2) continue;
      const m = ledAt(c.a);
      for (const o of [-1, 0, 1]) marks[(m + o + LEDS) % LEDS] = RING_RGB[c.r];
    }
    const hitAt = {};
    for (const h of S.hits) {
      const age = now - h.t0;
      const env = age < .01 ? age / .01 : age < .05 ? 1 : Math.pow(1 - (age - .05) / .15, 2);
      for (const [o, b] of HIT) {
        const i = (h.i + o + LEDS) % LEDS, a = b * env;
        if (!hitAt[i] || hitAt[i][1] < a) hitAt[i] = [h.rgb, a];
      }
    }
    // 录制倒计时与打板覆盖在最上层
    let rec = null;
    if (S.rec) {
      const e = now - S.rec;
      if (e < 3) rec = { seg: 3 - Math.floor(e) };
      else if (e < 3.25) rec = { flash: true };
    }
    for (let i = 0; i < LEDS; i++) {
      let rgb = white, a = 0;
      if (!S.playing && !CARDINAL[i]) a = .1 * breath * (th.idleGain || 1);
      if (S.playing) {
        const behind = (head - i + LEDS) % LEDS;
        if (behind < TRAIL.length) a = TRAIL[behind];
        if (marks[i] && a < (th.markA || .25)) { rgb = marks[i]; a = th.markA || .25; }
      }
      if (hitAt[i] && hitAt[i][1] > a) [rgb, a] = hitAt[i];
      if (CARDINAL[i]) { rgb = CARDINAL[i]; a = .75 + .25 * breath; }
      if (rec) {
        if (rec.flash) { rgb = white; a = 1; }
        else { const seg = Math.floor(i / 36); if (seg < rec.seg) { rgb = th.countdown || [220, 60, 50]; a = 1; } else a = Math.min(a, .05); }
      }
      const shown = rgb === white ? white : rgb;
      L[i].setAttribute('fill', mix(off, shown, Math.min(1, a * (th.gain || 1))));
      H[i].setAttribute('fill', `rgb(${(rgb === white ? (th.whiteHalo || white) : rgb).join(',')})`);
      H[i].setAttribute('opacity', (a * (th.haloA ?? .5)).toFixed(3));
    }
  }

  let lastZones = 0;
  function zonesFrame(now) {
    if (now - lastZones < .08) return;
    lastZones = now;
    for (const k in Z) {
      const r = +k[0];
      const empty = r < 2 && th.ctrlTint ? th.ctrlTint : 'transparent';
      if (th.tiles) {
        // 压力线性映射到明度：0 = 空白格，1 = 满量程（墨色）
        let p;
        if (S.mode === 'mock') p = (S.stones.has(k) ? 1 : 0) + (r < 2 ? S.ctrlExtra * .6 : 0);
        else p = (heatMap[k] || 0) * (heatMap[k] ? .96 + .04 * Math.sin(now * 2.1 + hash(k)) : 0) + .018 * (Math.sin(now * 1.3 + hash(k)) * .5 + .5);
        p = Math.max(0, Math.min(1, p));
        Z[k].setAttribute('fill', mix(r < 2 && th.tileCtrl ? th.tileCtrl : th.tileEmpty, th.tileFull, p));
      } else if (S.mode === 'mock') {
        const occ = th.occColor ? th.occColor : `rgba(${RING_RGB[r].join(',')},${th.occA ?? .14})`;
        Z[k].setAttribute('fill', S.stones.has(k) ? occ : empty);
      } else if (th.quietHeat) {
        // 安静的热度：只显示明显的压力，不画底噪；占用的区域由石头标记表达
        const base = heatMap[k] || 0;
        const p = base * (.9 + .1 * Math.sin(now * 2.1 + hash(k)));
        Z[k].setAttribute('fill', p > .1 ? `rgba(${(th.heat || [0, 0, 0]).join(',')},${(p * (th.heatA ?? .2)).toFixed(3)})` : empty);
      } else {
        const base = heatMap[k] || 0;
        const p = base ? base * (.86 + .14 * Math.sin(now * 2.1 + hash(k))) : .025 * (Math.sin(now * 1.3 + hash(k)) * .5 + .5);
        const rgb = th.heatByRing ? RING_RGB[r] : (th.heat || [0, 0, 0]);
        Z[k].setAttribute('fill', `rgba(${rgb.join(',')},${(p * (th.heatA ?? .5)).toFixed(3)})`);
      }
    }
  }

  const live = name => document.querySelectorAll(`[data-live="${name}"]`);
  const setLive = (name, v) => live(name).forEach(el => { if (el.textContent !== v) el.textContent = v; });
  function readouts(ctrl) {
    const bar = Math.floor(S.t / 2), seg = Math.floor(bar / 8);
    setLive('state', tr(S.playing ? 'playing' : 'idle'));
    setLive('chord', S.playing ? CHORDS[bar % 4] : '—');
    setLive('bar', `${String(bar + 1).padStart(2, '0')} / ${BARS}`);
    setLive('barN', String(bar + 1).padStart(2, '0'));
    setLive('section', S.playing ? FORM[seg] : '—');
    setLive('lofi', `${Math.round(ctrl * 100)}%`);
    setLive('stones', String([...S.stones].filter(k => +k[0] >= 2).length));
    setLive('voices', S.playing ? String(Math.min(48, 4 + [...S.stones].length * 2)) : '2');
    setLive('elapsed', mmss(S.t));
    setLive('ctrl', `${Math.round(ctrl * 100)}%`);
    document.body.classList.toggle('is-playing', S.playing);
    document.querySelectorAll('[data-form] [data-i]').forEach(el => {
      const i = +el.dataset.i;
      el.classList.toggle('on', S.playing && i === seg);
      el.classList.toggle('done', i < seg);
    });
    document.querySelectorAll('[data-bar-fill="form"]').forEach(el => { el.style.width = `${(S.t / (BARS * 2)) * 100}%`; });
    document.querySelectorAll('[data-bar-fill="lofi"]').forEach(el => { el.style.width = `${ctrl * 100}%`; });
    document.querySelectorAll('[data-ticks="lofi"]').forEach(el => {
      const n = el.children.length;
      [...el.children].forEach((c, i) => c.classList.toggle('on', i < Math.round(ctrl * n)));
    });
    let recText = '';
    if (S.rec) {
      const e = performance.now() / 1000 - S.rec;
      recText = e < 3 ? String(3 - Math.floor(e)) : mmss(e - 3);
    }
    setLive('recTime', recText);
    document.body.classList.toggle('is-rec', !!S.rec);
  }

  let last = performance.now();
  function frame(ms) {
    const dt = Math.min(.1, (ms - last) / 1000);
    last = ms;
    const now = ms / 1000;
    const { ctrl, ang } = step(dt, now);
    ledFrame(now, ang);
    zonesFrame(now);
    readouts(ctrl);
    requestAnimationFrame(frame);
  }

  // ── 页面上的控件 ──
  document.addEventListener('click', e => {
    const a = e.target.closest('[data-act]');
    if (!a) return;
    const act = a.dataset.act;
    if (act === 'clear') { S.stones.clear(); S.ctrlExtra = 0; document.querySelectorAll('[data-ctrl]').forEach(i => { i.value = 0; }); stonesChanged(); }
    if (act === 'record') S.rec = S.rec ? null : performance.now() / 1000;
    if (act === 'lang') { S.lang = a.dataset.langBtn || other(); apply(); }
    if (act === 'nav') { S.page = a.dataset.page; apply(); document.querySelector('.app')?.scrollTo(0, 0); window.scrollTo(0, 0); }
    if (act === 'arr') document.querySelectorAll('[data-act="arr"]').forEach(x => x.classList.toggle('active', x === a));
    if (act === 'tone') { a.classList.add('pulse'); setTimeout(() => a.classList.remove('pulse'), 600); }
  });
  document.addEventListener('input', e => {
    if (e.target.matches('[data-ctrl]')) S.ctrlExtra = e.target.value / 100;
  });

  window.SM = { S, tr, pick, VALUES, I18N };
  buildMat();
  stonesChanged();
  apply();
  requestAnimationFrame(frame);
})();
