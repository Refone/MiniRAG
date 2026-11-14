# MiniRAG 系统架构图

依据当前仓库实现绘制的组件级架构图（Archify `architecture`，showcase 质量档）。
静态阅读版即交付 HTML：交互运行时不依赖网络，明暗主题、缩放平移、搜索聚焦、关系追踪与引导视图均可用。

## 文件

| 文件                          | 说明                                                       |
| ----------------------------- | ---------------------------------------------------------- |
| `minirag-architecture.html`   | 交付产物：自包含交互式 HTML（内联 SVG）                    |
| `minirag-architecture.json`   | Archify 规格源文件；改图后重新 `deliver` 即可              |
| `minirag-architecture-v3.svg` | 双主题静态 SVG：保留 v2 布局，优化明暗配色与文字对比度     |
| `minirag-repository-structure.svg` | 仓库目录与职责的文字版速览，不表示系统架构关系 |
| `README.md`                   | 本说明                                                     |
| `THIRD_PARTY_NOTICES.md`      | 仓库结构 SVG 所内嵌图标的版权与许可证声明                   |

`minirag-repository-structure.svg` 的图标内嵌自
[vscode-material-icon-theme](https://github.com/material-extensions/vscode-material-icon-theme)，
固定来源为 commit `ced21b9b5241c1efa502a8c46ec7363a690a7058`；SVG 可离线独立显示。
版权与完整 MIT 许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

`minirag-architecture-v3.svg` 随系统明暗模式自动切换，独立于交互式 HTML 维护；
下方重新生成命令仅针对 HTML，不会更新该 SVG。

验收截图不随仓库保留；需要复查时按下方命令重新生成。

## 图意

系统架构（分层、主链路、运行态、存储与外部依赖）见 [docs/architecture.md](../../docs/architecture.md)；
本目录只负责图本身。为保持主链路可读，图中省略了 `api` / `service` 对 `common` 的直连
（schema、events、store 等）。

引导视图提供四条阅读路径：请求主链路、文档导入链路、问答检索链路、运行态与存储。

## 标签约定

- 主链路保留语义标签（`HTTP`、`反代`、`调用`、`编排`、`访问器`）。
- `common` 到数据 / 外部依赖的扇出箭头**有意不标关系文字**：目标节点副标题已写明
  用途（混合向量、制品、历史 / 计量、LLM、Embedding/Rerank/VLM、PDF → Markdown、
  联网检索），外部区域标签另注明 `HTTPS`。避免 7 条同类依赖边堆叠重复文案。
- 浏览器到 nginx 标 `HTTP`：`frontend/nginx.conf` 监听 80，Compose 映射 8080，
  仓库内未终止 TLS。若部署在 TLS 反向代理之后，请同步改这条标签。
- `common` 节点折叠了 config / logging / prompt / schema / utils 等子模块；
  etcd、Attu 属于 Milvus 内部或运维组件，未在图中展开。

## 事实来源

- 后端分层与图结构：`backend/api/`、`backend/service/`、`backend/graphs/`、
  `backend/common/`
- 前端与反代：`frontend/nginx.conf`、`frontend/src/App.tsx`
- 编排与基础设施：`docker/compose.infra.yaml`、`docker/compose.backend.yaml`、
  `docker/compose.frontend.yaml`
- 外部服务地址：`backend/common/config/env_config.py`
- 分层约束：`docs/architecture.md`、`tools/check_layers.py`

## 重新生成与验收

在仓库根目录执行：

```shell
node ~/.agents/skills/archify/bin/archify.mjs validate architecture \
  assets/architecture/minirag-architecture.json --quality showcase

node ~/.agents/skills/archify/bin/archify.mjs deliver architecture \
  assets/architecture/minirag-architecture.json \
  assets/architecture/minirag-architecture.html --quality showcase

# 视觉验收：1440×900 / 1600×1000 / 1920×1080 / 2048×1320 容器与截图
ARCHIFY_CHROME_NO_SANDBOX=1 node ~/.agents/skills/archify/bin/archify.mjs \
  visual-check assets/architecture/minirag-architecture.html
```

> `ARCHIFY_CHROME_NO_SANDBOX=1` 只用于 Chrome 自身沙箱无法初始化的环境
> （如受限的 agent 沙箱）。普通桌面环境直接运行 `visual-check` 即可。

当前交付回执：

```text
diagram_type: architecture
validation: 9/9 showcase, 0 errors, 0 warnings
specification_sha256: 84c365c6acbb246915950e99bac6d7dc96a9f8ead34a1c5f60c9288c7e6adcc2
artifact_sha256: a7b0d664d1fe5b0007558604693ed81d50dd6e5d97875d24c1034ba545dad445
visual_check: pass（四个视口无横向/纵向溢出；明暗主题截图已人工走查）
visual_review: passed
```

视觉检查的最小投影节点文字约为 6.15px（1440×900，读取态），2048×1320 下约为
8.2px；如需放大阅读，可使用查看器内置缩放。
