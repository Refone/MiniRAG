---
name: interactive-demo
description: 根据 PRD / 需求文档为 MiniRAG 生成可评审的前端交互 demo（demo.html）：单文件、离线可双击、明暗双主题、mock 数据、所有状态可直达。当用户要「交互 demo / 前端交互demo / 交互原型 / 原型页面 / demo.html / 页面布局与动效预览」，或需求开发 SOP 走到「前端交互demo」阶段时使用。
whenToUse: 需要把 docs/feat/<需求名>/PRD.md 的页面需求可视化，或迭代已有 demo.html 的某个状态时。
---

# 前端交互 demo（demo.html）

把需求文档转成**评审可直接双击打开**的单文件原型，呈现「页面布局 + 动画效果 + 交互逻辑」。
原型只回答「长什么样、怎么动、点了会怎样」：不写真实接口、不接后端、不提前改 `web/src`。

## 产出契约

| 项 | 约定 |
| --- | --- |
| 路径 | `docs/feat/<需求名>/demo.html`（与 PRD 同目录，目录不存在就建） |
| 形态 | 单文件、零依赖、`file://` 双击可开；不新增图片文件（图标内联 SVG，图片用内联 SVG/渐变占位） |
| 规模 | 模板自带约 950 行（令牌 + 骨架 + 示例），替换示例后通常 900–1500 行；超过 1800 行先考虑拆状态或按 tab 分组 |
| 数据 | 全部 `MOCK` 常量，MiniRAG 语境（知识库、文档、分块、检索、导入任务），不用 lorem ipsum |
| 归属 | AI 只写文件，不 `git add/commit`；人类评审通过后才动 `web/src` 和后端改动方案 |

多页面需求仍是**一个** demo.html，页内用顶栏 tab 或横向滑轨切换；默认不要产出第二个 html。

## 工作流

### 1. 读需求（只读必要文件）

- `docs/feat/<需求名>/PRD.md`：正文 + 文末「评审纪要 / 补充要求」，两侧同等有效。
- 已有后端方案（如 `后端改动方案.md`）时读其验收条件章节补状态；没有就不创建。
- 抽出四类信息，缺一项就回看原文，不脑补：**页面/区域、状态、交互、文案**。
- 现有 demo.html 时先读它，做**增量**改动并保留已有状态，不推翻重写。

### 2. 对齐现状（让原型像真产品）

读被改动区域的 `web/src`（`pages/`、`components/`、`styles/`），沿用同样的 DOM 轮廓、文案语气与视觉令牌：

- 令牌唯一来源 `web/src/styles/tokens.css`；模板已内联一份，生产变更时覆盖过去。
- 关键尺寸、组件配方、图标规则见 `references/design-system.md`。
- 页面骨架（navbar、对话区 `max-width: 800px`、文档页左栏 `360px`）照抄，不要自创导航。

### 3. 先定「演示脚本」，再写代码

动手前在回复里给一张 3–8 行的表，让人类先看你要演什么：

| 状态键 | 触发 | 验证点 |
| --- | --- | --- |
| `empty` | 演示控件 / `?state=empty` | 空态文案与主 CTA |
| `streaming` | 「发送」后自动进入 | 逐字输出、停止按钮、引用来源 |
| `failed` | 演示控件 | 错误文案、重试入口 |

约束：

- PRD 每个 P0 需求点至少对应一个**可达**状态；P1 状态按评审价值取舍，别堆二十个按钮。
- 每个状态都能从演示控件点到，不依赖自动播放。
- 前后对比类需求（页面美化/重构）在同一文件内可切换，方便对照截图。

### 4. 落地代码

```bash
mkdir -p docs/feat/<需求名>
cp .agents/skills/interactive-demo/assets/demo-template.html docs/feat/<需求名>/demo.html
```

以模板为骨架（主题、导航、演示控件、URL 参数、定时器管理都已就绪）：`cp` 到目标路径后**在模板基础上改**，不要整文件读进上下文——只 `read` 你要替换的 `<!-- ↓↓↓ 需求页面 ↓↓↓ -->` 区块与对应 JS 段；按 `references/design-system.md` 组装页面、按 `references/interaction-patterns.md` 实现交互，再逐条满足下面的硬性规则。

### 5. 自检（必须真跑，不能目测）

```bash
# 外链资源：期望无输出（data URI 的 xmlns 不算）
grep -nE '(src|href)="(https?:)?//' docs/feat/<需求名>/demo.html
grep -nE "url\(\s*[\"']?https?:" docs/feat/<需求名>/demo.html
# 网络请求：期望无输出
grep -nE 'fetch\(|XMLHttpRequest|EventSource|new WebSocket' docs/feat/<需求名>/demo.html
```

浏览器逐状态走查（DSH 用 `browser_open` / `browser_read` / `browser_console` / `browser_screenshot`；没有工具就 `open` 后按同一清单人工核对）：

1. `?state=<每个状态>` 各开一次：console 无 error、无失败请求。
2. `?theme=dark` 与 `?theme=light` 各截一张；390px 窄屏再截一张（无横向滚动）。
3. 点一遍：演示控件、状态切换、重播、主按钮、弹窗（Esc 关闭）、tab/视图切换。
4. `browser_read` 核对文案与 PRD 一致（按钮措辞、单位、错别字）。
5. 回归：切到 A 再切回 B 仍可达；重播后无残留定时器/动画/toast。

### 6. 交付

最终回复必须包含：

- 「需求点 → 演示路径」对照表（`?state=xx` 或「点击 xx」）；
- 原型假设（PRD 没写、按现有模式补的交互）与明确未覆盖项；
- 下一步提示：按 SOP 写「后端改动方案.md」（技能 `backend-plan`），demo 定稿后再动代码。

只说「已生成」不算交付。

## 硬性规则（评审当场会挑的）

1. **离线单文件**：无 CDN、无外链字体/图片、无 `fetch`；不引用 `web/` 里的文件。
2. **主题**：`<html data-theme>` + `<head>` 内联脚本先定主题（防闪白），键名 `minicrag-preview-theme`；右上角可切换；深色下不得出现白卡片、黑字、看不见的边框。
3. **只用令牌**：颜色/圆角/阴影全部走 `--bg/--surface/--text/--accent/--r-*/--shadow-*`；确需新色，同时加到 `:root` 与 `[data-theme="dark"]` 并起语义名。
4. **交互真能点**：hover / active / focus-visible 齐全；弹窗 Esc 关闭并还原焦点；toast 自动消失；输入框能打字（回车发送）；tab 能切。
5. **状态可达**：不只画终态；空、加载、失败、终态至少各一个，且都能从控件直达。
6. **动画克制**：过渡 120–250ms；流式/进度必须有终止条件；`prefers-reduced-motion: reduce` 全部降级（含骨架脉冲与旋转图标）。
7. **可截图**：支持 `?theme=light|dark`、`?state=<key>`、`?clean=1`（隐藏演示控件）、`?static=1`（暂停自动播放）。
8. **演示控件**：固定右上（navbar 下方），虚线边框 + 「原型演示」标签 + 状态按钮 + 重播 + 隐藏；不属于产品 UI，`aria-label` 齐全，`?clean=1` 时整体隐藏。
9. **响应式**：1280 / 768 / 390 三档不溢出、不遮挡；窄屏导航折行、侧栏折叠/抽屉。
10. **定时器可回收**：所有 `setTimeout/setInterval` 走 `later()/clearTimers()`，重播/切状态先清空；toast 的销毁用独立 timer，别被误清。
11. **写法**：无文件头注释；CSS/JS 用 `/* ==== 区块 ==== */` 分节；JS 单 IIFE，模板用 `var`，同一文件内保持统一；不刷 console.log（关键交互留一条 `[demo]` 日志可以）。

## 反模式

- 只做「完美终态」：加载/失败不可见，评审无法判断异常体验。
- 用绝对像素坐标摆布局：换个视口就崩，用 flex/grid。
- 复制 2600 行生产 CSS，或引入 React/Vue CDN：离线打不开/超重。
- 固定 `100vh`：移动端地址栏会裁掉底部，用 `100dvh`（模板已处理）。
- 无限循环装饰动画（加载态除外）。
- 把 PRD 段落成篇贴进页面：原型是界面，不是文档。
- 顺手改 `web/src` 或提前写方案设计：越阶段。

## 参考

- `assets/demo-template.html`：可运行骨架（令牌 / 导航 / 主题 / 演示控件 / URL 参数 / 定时器 / 示例任务卡）。
- `references/design-system.md`：令牌、排版、间距、组件配方（按钮、徽标、弹窗、toast、骨架、空态、分段开关）。
- `references/interaction-patterns.md`：状态机、流式回答、任务步骤、上传拖拽、删除确认、视图切换、必做状态清单、常见坑。
- 既有原型（风格基准）：`docs/feat/任务管理升级/demo.html`、`docs/feat/页面美化/chatpage.html`、`docs/feat/页面美化/importpage.html`。
- SOP：`AGENTS.md`「需求开发 SOP」。
