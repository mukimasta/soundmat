# Console App

网页控制台是 `console/` 下的独立前端工程：React 19、Vite 6、TypeScript，测试用 Vitest 与 Testing Library（jsdom）。界面行为见 `design/CONSOLE.md`，视觉以设计稿 `design/SoundMat 控制台.html` 为准；与主机程序的协议见 `CONTROL_API.md`。

## 开发与构建

```bash
cd console
npm ci
npm run dev      # 开发服务器；/api 与 /ws 转发到 127.0.0.1:8000（可用 SOUNDMAT_HOST 改）
npm test         # 单元与组件测试
npm run build    # 类型检查并构建到 console/dist，由主机程序直接提供
```

`console/dist` 不提交；部署前在开发机上构建。

## 结构

1. `src/api/client.ts`：`SoundMatClient` 维护唯一的 WebSocket 连接和界面状态（`ConsoleState`），断开时清掉所有实时数据并每秒重连；`reduce` 是纯函数，便于测试。命令通过 `post` 发出。
2. `src/api/context.tsx`：用 `useSyncExternalStore` 把客户端状态接入 React（`useConsole`、`useClient`）。
3. `src/api/patch.ts`：把点号路径的变化应用到状态树。
4. `src/components/`：垫面绘图 `MatView`（SVG，坐标与主机程序的区域几何一致）、顶部横幅等。
5. `src/pages/`：各页面。
6. `src/theme.css`：设计稿的颜色与字体。

## 面板的键盘与焦点

底部面板（`components/Sheet.tsx`）打开时把焦点移到面板本身（`role="dialog"`、`tabIndex=-1`），按 Esc 关闭，关闭后焦点回到打开它的按钮。从菜单进入设置或已录制时，菜单面板先关闭、焦点先回到底部的菜单按钮，新面板再取得焦点，所以最后关闭时焦点仍回到菜单按钮。

## 字体

设计稿用 Hanken Grotesk、JetBrains Mono 和 Noto Sans SC。前两者通过 `@fontsource` 打包进构建产物，装置离线时也能显示；Noto Sans SC 体积太大，不打包，中文回退到手机和电脑自带的中文字体（苹方、冬青黑体、微软雅黑）。

## 垫面绘图

压力按"满量程的一半显示为最深色"着色（石头的读数通常远低于满量程），从底色向每环的代表色过渡；每环代表色与第一版 Jam 灯光一致。
