# 设计系统速查（MiniRAG）

原型的视觉必须和真实前端一致，评审才不会把「原型的临时样式」当成需求。
唯一来源是仓库里的样式文件，本文件只是**给 demo 用的摘录**：

- 令牌：`frontend/src/styles/tokens.css`
- 基础：`frontend/src/styles/base.css`
- 骨架/导航：`frontend/src/styles/layout.css`
- 通用组件：`frontend/src/styles/ui.css`
- 页面：`frontend/src/styles/chat.css`、`frontend/src/styles/docs.css`

生产令牌变更时，用 `tokens.css` 覆盖 `assets/demo-template.html` 里的令牌块；不要在 demo 里另造一套色板。

## 1. 令牌

| 令牌 | 浅色 | 深色 | 用途 |
| --- | --- | --- | --- |
| `--bg` | `#f4f5f7` | `#1b1b1f` | 页面底色 |
| `--bg-nav` | `#ffffff` | `#161618` | 导航栏 |
| `--surface` | `#ffffff` | `#202127` | 卡片/弹窗 |
| `--surface-2` | `#fafbfc` | `#26272e` | 次级面板 |
| `--surface-hover` | `#f1f2f5` | `#2a2b32` | hover 底 |
| `--surface-inset` | `#eceef1` | `#161618` | 分段开关底/空徽标 |
| `--border` | `#e4e6eb` | `#2e2e32` | 常规描边 |
| `--border-strong` | `#d3d7dd` | `#3c3f44` | hover 描边/滚动条 |
| `--text` | `#1f2328` | `#dfdfd6` | 主文字 |
| `--text-2` | `#646c7b` | `#98989f` | 辅助文字 |
| `--text-3` | `#8b93a1` | `#6f7076` | 弱化文字/未激活 |
| `--accent` | `#4f46e5` | `#a8b1ff` | 强调（浅色文字用 accent 本身） |
| `--accent-fill` | `#4f46e5` | `#5a68dd` | 填充按钮/logo |
| `--accent-soft` | `#eef2ff` | `rgba(100,108,255,.16)` | 选中底 |
| `--accent-border` | `#c7d2fe` | `rgba(168,177,255,.35)` | 选中描边 |
| `--on-accent` | `#ffffff` | `#ffffff` | 填充按钮上的字 |
| `--focus` | `#4f46e5` | `#a8b1ff` | 焦点环 |
| `--success`/`-soft` | `#15803d`/`#dcfce7` | `#3dd68c`/`rgba(16,185,129,.16)` | 成功 |
| `--warning`/`-soft` | `#b45309`/`#fef3c7` | `#f9b44e`/`rgba(234,179,8,.14)` | 进行中/注意 |
| `--danger`/`-soft` | `#b91c1c`/`#fee2e2` | `#f66f81`/`rgba(244,63,94,.16)` | 失败/危险操作 |
| `--user-bubble` | `#e9ebef` | `#2a2b32` | 用户气泡 |
| `--mask` | `rgba(15,23,42,.40)` | `rgba(0,0,0,.55)` | 弹窗遮罩 |
| `--r-xs…--r-2xl` | 4/6/8/10/12/16 | 同 | 圆角 |
| `--shadow-card/1/2` | 见 tokens | 深色下减弱或 `none` | 阴影 |

规则：颜色一律走变量；新增色调必须同时写进 `:root` 与 `[data-theme="dark"]` 并起语义名。

## 2. 排版

| 层级 | 字号/字重 | 备注 |
| --- | --- | --- |
| 页面主标题 | 16px / 650 | 弹窗标题、空态标题 |
| 卡片标题 | 14px / 650 | 单行截断 |
| 正文 | 13–15px / 400 | 对话正文 15px，列表 13px |
| 辅助 | 12–12.5px | 时间、大小、计数 |
| 微 | 11–11.5px | 徽标、演示控件、快捷键 |

- 行高：正文 1.6–1.7，标题 1.2–1.4。
- 字体：`var(--font-sans)`；代码/数字表格用 `var(--font-mono)`。
- 中文文案：全角标点；省略号用「…」；数字与单位留空格（`2.4 MB`、`128 个分块`）；按钮用动宾短语（`开始导入`/`重新导入`/`重试`/`停止生成`）；不要中英混排的「OK/Yes」。
- 文案必须来自 PRD；PRD 没给的提示语按上面的语气补，并在交付时列为假设。

## 3. 间距与圆角

- 4 的倍数为主：4 / 6 / 8 / 10 / 12 / 16 / 20 / 24。
- 页面内边距 16–20；卡片内边距 16–20；卡片间距 12–16；控件组内 gap 4–8。
- 圆角：按钮/输入 `--r-md`，小卡/列表项 `--r-lg`，面板 `--r-xl`，浮层/大卡 `--r-2xl`，徽标 `--r-pill`。

## 4. 布局事实

| 区域 | 事实 |
| --- | --- |
| 应用骨架 | `.app-shell` 纵向 flex、`100dvh`；`.app-body` 横向 flex、`min-height: 0` |
| 导航栏 | padding `12px 20px`，logo `36px`，tabs `gap: 4px`；≤720px 折行、tab 均分整行 |
| 对话页 | `.chat-inner` `max-width: 800px`；消息 padding `26px 20px 0`；用户气泡 `max-width: 78%` |
| 输入区 | 悬浮在底部，`.composer-wrap` 用渐变遮罩 + 消息区 `padding-bottom` 留白；textarea 自增高（上限 160px） |
| 文档页 | `.docs-page` `display: flex; gap: 16px; padding: 16px`；左栏固定 `360px`，右侧预览 `max-width: 820px` |
| 长列表 | 滚动容器自己滚（`min-height: 0`），页面外层不滚 |
| 窄屏 | 侧栏折叠/抽屉；用户气泡 `88%`；导航折行；演示控件贴边折行 |

## 5. 组件配方

按顺序抄，命名保持生产一致（`.panel`、`.badge`、`.btn` 等），方便对照实现。

### 按钮

```css
.btn { border: 1px solid var(--border); background: transparent; padding: 7px 14px;
       border-radius: var(--r-md); font-size: 13px; color: var(--text);
       transition: background-color .15s, border-color .15s, transform .05s; }
.btn:hover:not(:disabled) { background: var(--surface-hover); border-color: var(--border-strong); }
.btn:active:not(:disabled) { transform: translateY(1px); }
.btn:disabled { opacity: .55; cursor: not-allowed; }

/* 危险主操作（删除确认）：生产里 .btn.primary 就是危险样式 */
.btn.primary { background: var(--danger-soft); border-color: transparent; color: var(--danger); }
.btn.primary:hover:not(:disabled) { border-color: var(--danger); }

/* 发送按钮：accent 圆形 */
.send { width: 32px; height: 32px; border: 0; border-radius: 50%;
        display: inline-flex; align-items: center; justify-content: center;
        color: var(--on-accent); background: var(--accent-fill); }
.send:disabled { opacity: .4; cursor: not-allowed; }
```

### 状态徽标

```css
.badge { display: inline-flex; align-items: center; gap: 5px; padding: 3px 9px;
         border-radius: var(--r-pill); font-size: 11.5px; font-weight: 600; }
.badge-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
.badge.is-idle       { background: var(--surface-inset); color: var(--text-2); }
.badge.is-processing { background: var(--accent-soft);  color: var(--accent); }
.badge.is-completed  { background: var(--success-soft); color: var(--success); }
.badge.is-error      { background: var(--danger-soft);  color: var(--danger); }
```

### Toast（左下角）

```css
.toast-host { position: fixed; left: 24px; bottom: 24px; z-index: 100;
              display: flex; flex-direction: column; gap: 8px; }
.toast { display: flex; gap: 8px; max-width: 340px; padding: 10px 14px;
         background: var(--surface); border: 1px solid var(--border);
         border-radius: var(--r-lg); box-shadow: var(--shadow-2); font-size: 13px;
         animation: toast-in .2s ease-out; }
.toast-dot { width: 8px; height: 8px; margin-top: 6px; border-radius: 50%; background: var(--accent); }
.toast.success .toast-dot { background: var(--success); }
.toast.error   .toast-dot { background: var(--danger); }
```

### 确认弹窗

```css
.modal-mask { position: fixed; inset: 0; z-index: 90; background: var(--mask);
              display: flex; align-items: center; justify-content: center; }
.modal { width: 380px; max-width: calc(100vw - 40px); padding: 20px;
         background: var(--surface); border: 1px solid var(--border);
         border-radius: var(--r-xl); box-shadow: var(--shadow-2); }
.modal h3 { margin: 0 0 10px; font-size: 16px; }
.modal p { margin: 0 0 14px; font-size: 13px; color: var(--text-2); line-height: 1.6; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; }
```

### 分段开关

```css
.segmented { position: relative; display: inline-grid; grid-auto-flow: column;
             grid-auto-columns: 1fr; gap: 2px; padding: 3px;
             background: var(--surface-inset); border-radius: var(--r-lg); }
.seg-btn { position: relative; z-index: 1; border: 0; background: transparent;
           padding: 6px 14px; border-radius: var(--r-md); font-size: 13px; color: var(--text-2); }
.seg-btn.active { color: var(--text); }
.seg-thumb { position: absolute; top: 3px; bottom: 3px; left: 3px; background: var(--seg-thumb);
             border-radius: var(--r-md); box-shadow: var(--shadow-seg);
             transition: transform .22s cubic-bezier(.4, 0, .2, 1); }
```

### 骨架屏

```css
.skeleton { border-radius: var(--r-md); background: var(--surface-2);
            animation: skeleton-pulse 1.4s ease-in-out infinite; }
@keyframes skeleton-pulse { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }
.sk-line { height: 14px; margin-bottom: 12px; }
.sk-line.w60 { width: 60%; } .sk-line.w80 { width: 80%; } .sk-line.w40 { width: 40%; }
```

### 空态

```css
.empty { display: flex; flex-direction: column; align-items: center; justify-content: center;
         gap: 10px; min-height: 320px; color: var(--text-2); text-align: center; }
.empty .icon { width: 40px; height: 40px; stroke-width: 1.4; color: var(--text-3); }
.empty-title { margin: 4px 0 0; font-size: 15px; font-weight: 600; color: var(--text); }
.empty-sub { margin: 0; font-size: 13px; color: var(--text-2); }
```

## 6. 图标

- 统一 16px 线性图标，`stroke-width: 1.8`，`fill: none`，颜色 `currentColor`。
- 用 `<symbol>` sprite + `<use href="#i-xxx" />`，模板里已带 chat/book/moon/sun/check/alert/refresh/x/doc/circle/spinner。
- 不引入图标库、不用 emoji 当图标（评审会当成最终视觉）。
