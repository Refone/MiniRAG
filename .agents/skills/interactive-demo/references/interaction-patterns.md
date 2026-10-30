# 交互模式库（demo 专用）

把 PRD 的交互翻译成可点击的模拟。所有片段都建立在 `assets/demo-template.html` 的骨架上：
`later()/clearTimers()` 管定时器、`applyState()` 管状态、`toast()` 管提示。

## 1. 状态机是原型的骨架

不要写「一串 onclick 改 DOM」，而是：**状态 → 一次性渲染全部相关 DOM**。
这样每个状态都能从演示控件直达，也不会有「切回来样式残留」。

```js
var STATES = [
  { key: "idle",    label: "未开始" },
  { key: "running", label: "处理中" },
  { key: "done",    label: "已完成" },
  { key: "failed",  label: "失败" }
];

function render() {
  stage.setAttribute("data-state", state);       // 需要按状态改样式时用 CSS 钩子
  badgeText.textContent = BADGE[state].text;     // 文案/徽标
  hint.textContent = HINT[state];
  actionBtn.disabled = state === "running";
  actionBtn.textContent = ACTION[state];
  // …列表、步骤、空态、骨架各自按 state 渲染
}

function applyState(next) {
  clearTimers();          // 先进新状态，再决定要不要起动画
  state = next;
  render();
}
```

要点：

- 每个状态显式设置依赖数据（如 `progress`），不要依赖上一个状态残留。
- 动画只由 `running` 类状态触发，`done`/`failed` 必须停下来。
- 演示控件按钮直接 `applyState(key)`，保证「所有状态可达」。

## 2. 流式回答（逐字输出）

```js
var typingTimer = null;

function streamAnswer(el, text, onDone) {
  var chars = Array.from(text);
  var i = 0;
  el.classList.add("is-streaming");
  typingTimer = window.setInterval(function () {
    i += 1 + Math.floor(Math.random() * 2);      // 1–2 字/帧，接近真实 token 节奏
    el.textContent = chars.slice(0, i).join("");
    if (i >= chars.length) {
      window.clearInterval(typingTimer);
      el.classList.remove("is-streaming");
      if (onDone) onDone();
    }
  }, 24);
}

function stopStream() {
  window.clearInterval(typingTimer);
  el.classList.remove("is-streaming");
  // 停止后保留已输出内容 + 显示「已停止生成」标记和「重新生成」按钮
}
```

- 光标用 `.is-streaming::after { content: "▍"; animation: blink 1s steps(2) infinite; }`。
- 「停止生成」按钮只在 `running` 可见；停止后按钮换成「重新生成」。
- 有 `prefers-reduced-motion: reduce` 时直接整段输出（或缩短到 100ms）。
- 长回答的滚动：容器贴底时 `scrollTop = scrollHeight`，用户手动上滑后不要再抢滚动。

## 3. 检索/工具步骤

```js
function renderSteps() {
  return MOCK.steps.map(function (text, i) {
    var kind = state === "done" || i < progress ? "done"
      : state === "failed" && i === progress ? "error"
        : state === "running" && i === progress ? "running"
          : "pending";
    return '<li class="step ' + kind + '">' + icon(kind) + "<span>" + text + "</span></li>";
  }).join("");
}
```

- 图标：`done` 对勾、`running` 旋转环、`failed` 警告、`pending` 空心圆。
- 计数文案：`已完成 3，进行中 1，状态：处理中`（来自 PRD 的措辞）。
- 终态常驻 + 自动收起成摘要行；**不要**在终态把步骤卡片整个删掉 —— 评审要看历史。
- 展开/收起用 `<details>` 或按钮切换，别用 hover。

## 4. 上传与拖拽

```js
zone.addEventListener("dragover", function (e) {
  e.preventDefault();
  zone.classList.add("is-over");
});
zone.addEventListener("dragleave", function () {
  zone.classList.remove("is-over");
});
zone.addEventListener("drop", function (e) {
  e.preventDefault();
  zone.classList.remove("is-over");
  var files = Array.prototype.slice.call(e.dataTransfer.files || []);
  files.forEach(function (file) {
    if (file.size > 50 * 1024 * 1024) { toast("《" + file.name + "》超过 50 MB", "error"); return; }
    addTask(file.name, file.size);       // 进任务列表，状态 uploading → processing → completed
  });
});
```

- 引入视图/列表视图切换用横向滑轨（见 §7），上传成功后自动滑到列表并 toast。
- 进度条用宽度百分比 + `transition: width .3s`；失败要能重试。

## 5. 删除确认与乐观更新

```js
function requestDelete(doc) {
  openModal({
    title: "删除文档？",
    body: "《" + doc.title + "》的 Milvus 索引与 MinIO 制品将一并移除，不可恢复。",
    confirmText: "删除",
    danger: true,
    onConfirm: function () { removeDoc(doc); }
  });
}

function removeDoc(doc) {
  var index = docs.indexOf(doc);
  docs.splice(index, 1);                 // 先移除（乐观）
  renderDocs();
  closeModal();
  toast("已删除《" + doc.title + "》", "success");

  // 失败场景由演示控件触发，不要用 Math.random —— 截图必须可复现
  if (demo.failNextDelete) {
    docs.splice(index, 0, doc);          // 回滚
    renderDocs();
    toast("删除失败，已恢复", "error");
  }
}
```

- 危险主操作按钮用 `.btn.primary`（本项目的 primary 就是危险红）。
- 弹窗打开后焦点进弹窗，Esc/遮罩关闭，关闭后焦点回到触发按钮。

## 6. Toast

```js
function toast(text, kind) {
  var el = document.createElement("div");
  el.className = "toast" + (kind ? " " + kind : "");
  var dot = document.createElement("span");
  dot.className = "toast-dot";
  var body = document.createElement("span");
  body.textContent = text;                 // 用 textContent，别拼 HTML
  el.append(dot, body);
  toastHost.appendChild(el);
  window.setTimeout(function () { el.remove(); }, 2600);  // 独立 timer，不会被 clearTimers 清掉
}
```

- 同类提示合并，最多同时 3 条。
- 失败用 `error`，成功用 `success`，普通信息不传 kind。

## 7. 视图/页面切换（横向滑轨）

```css
.stage { overflow: hidden; }                       /* 外层不滚，轨道滚动 */
.track { display: flex; width: 200%; height: 100%; transform: translateX(-50%);
         transition: transform .45s cubic-bezier(.33, 1, .68, 1); }
.stage.show-a .track { transform: translateX(0); }
```

- 两视图各自内部滚动（`min-height: 0`），切回来保留滚动位置。
- 顶栏 tab 用 `.tab.active` + `aria-current="page"`；模板已接好 `data-page` / `data-slot` 的 tab 切换，多页面直接加 slot 与 tab。

## 8. 主题、URL 参数、演示控件

模板已经实现，别另写一套：

| 参数 | 作用 |
| --- | --- |
| `?theme=light\|dark` | 固定截图主题（同时写入 localStorage） |
| `?state=<key>` | 直接定格到某状态，禁止自动播放 |
| `?clean=1` | 隐藏演示控件（交截图/录屏用） |
| `?static=1` | 暂停自动推进 |
| `?page=<key>` | 直接切到模板里的某个 tab 页（多页面需求） |

规则：主题在 `<head>` 内联脚本里先定（防闪白），键名沿用 `minicrag-preview-theme`。

## 9. 键盘与焦点

- 弹窗：`Esc` 关闭，打开时焦点进第一个可操作项，关闭后还原。
- 只有演示控件时，`Esc` 隐藏控件（模板行为）；有弹窗时把 `Esc` 让给弹窗。
- 所有图标按钮带 `aria-label`；纯图标 + 文字的按钮不需要。
- 不用 `tabindex` 正数；`focus-visible` 样式用全局的。

## 10. 场景 → 必做状态

| 需求类型 | 至少覆盖 |
| --- | --- |
| 列表/管理页 | 空态、加载骨架、有数据、搜索无结果、长标题截断、删除确认、删除成功、删除失败回滚 |
| 导入/上传 | 待上传、拖拽悬停、上传中进度、校验失败（超大/格式）、成功后切换视图、任务失败重试 |
| 对话/检索 | 空会话引导、流式生成中（可停止）、检索步骤、引用来源、错误气泡 + 重试、历史加载 |
| 长任务/流程 | 进行中步骤推进、成功终态常驻、失败重试、中止确认 |
| 页面美化/重构 | 旧/新对照（切换）、深色、窄屏、关键组件 hover/选中/禁用 |

## 11. 常见坑

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| 深色主题出现白卡片/黑字 | 硬编码颜色 | 全部换成 `var(--surface/--text/…)` |
| 窄屏出现横向滚动条 | 固定宽度、绝对定位、长单词 | `max-width: 100%`、`flex-wrap`、`min-width: 0`、`overflow-wrap` |
| 最后一条消息被输入区挡住 | 底部留白不足 | 容器 `padding-bottom` = 输入区高度 + 缓冲，随高度变化同步 |
| 重播后动画叠加/文案错乱 | 旧定时器没清 | 统一 `later()/clearTimers()`，重播先清 |
| 首帧闪白/闪黑 | 主题在 DOM 之后才设 | `<head>` 内联脚本先定 `data-theme` |
| 移动端底部被地址栏裁掉 | `100vh` | `height: 100dvh`（保留 `100vh` 兜底） |
| toast 不消失 | 被 `clearTimers()` 清掉了销毁定时器 | toast 用独立 `setTimeout` |
| 切状态后进度条卡住 | `applyState()` 没重置进度/禁用态 | 每个状态显式初始化依赖数据 |
