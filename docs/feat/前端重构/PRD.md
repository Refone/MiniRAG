# 前端重构 PRD

<!-- docs-layout: 2026-11 -->
> 状态：已完结（历史快照） · 文中 `src/`、`web/` 为 2026-11 目录改名前的路径，当前对应 `backend/`、`frontend/`；代码现状以仓库为准。索引见 [docs/feat/README.md](../README.md)。

## 现状

当前的前端代码主要结构如下:

```shell
web/                        # 前端工程根目录
├── ...
└── src/                    # 前端应用源码
    ├── App.tsx                 # 应用外壳与页面切换
    ├── main.tsx                # React 挂载入口
    ├── vite-env.d.ts           # Vite 环境类型声明
    ├── components/             # 页面共用组件
    │   ├── CompleteIcon.tsx        # 完成状态图标
    │   ├── FailedIcon.tsx          # 失败状态图标
    │   ├── LoadingIcon.tsx         # 加载状态图标
    │   ├── Markdown.tsx            # Markdown 内容展示
    │   └── NavBar.tsx              # 顶部导航栏
    ├── lib/                    # API、类型和通用辅助逻辑
    │   ├── api.ts                  # 后端 API 请求封装
    │   ├── chatUtils.ts            # 聊天消息处理工具
    │   ├── imageCache.ts           # 图片缓存与 URL 管理
    │   ├── requestCache.ts         # 请求结果缓存
    │   ├── scrollRestore.ts        # 滚动位置恢复 Hook
    │   └── types.ts                # 前端共享类型定义
    ├── pages/                  # 应用页面
    │   ├── ChatPage.tsx            # 问答聊天页面
    │   └── ImportPage.tsx          # 文档导入与管理页面
    ├── stores/                 # Zustand 状态管理
    │   ├── chatStore.ts            # 聊天消息、会话及历史状态
    │   ├── docsStore.ts            # 文档列表、导入任务等状态
    │   └── sessionStore.ts         # 会话相关状态
    ├── styles/                 # 全局与图标样式
    │   ├── global.css              # 全局基础样式
    │   └── icon.css                # 图标样式
    └── theme/                  # 主题相关逻辑
        └── ThemeContext.tsx    # 明暗主题状态与 Provider
```

存在的问题有:

1. 代码结构不清晰
   - 大量逻辑杂糅在两个 pages 页面中, 明明有很多可以抽象出来的 components, 但是 components 目录中却很少有实际组件。
   - lib 目录也属于大杂烩目录, 包含了 API 请求、缓存、工具函数等多种逻辑, 缺乏清晰的分层和组织。

2. 储存、常量管理分散
   - stores 中分类的依据应该是不同方式的缓存, 而不是功能模块, 这样更有利于状态的复用和管理。
   - 很多常量分散在各个文件中, 较好的做法是将常量集中管理, 便于维护复用。

## 目标

参考这样一个目录结构:

```shell
web/
└── src/
    ├── components/    # UI 组件（将 App 中用到的组件抽象出来，尽量复用）
    ├── pages/         # 路由页面（具体页面，对应本项目 ChatPage 和 ImportPage）
    ├── store/         # 本地状态存储（根据存储方式分不同文件）
    ├── lib/           # 配置好的、跨模块复用的基础设施代码
    ├── styles/        # 全局样式入口
    ├── hooks/         # 被多个页面或组件共享的全局 Hooks
    ├── types/         # 跨模块、全局性的类型契约, 例如接口定义、枚举等
    └── utils/         # 工具函数, 与业务相关性不大的通用逻辑
```

分析与解构当前前端项目，分门别类把对应逻辑放到正确位置，完成前端项目重构。

## 要求

- 如果两个组件当前视觉上存在细小差异，但逻辑高度类似，偏向于整合为一个组件，容忍 UI 细微改动。
- 切分粒度适中，避免本该在一个文件中的逻辑，被过度切分为多个文件。
- 尽量保持集成逻辑的清爽，如 pages 中的文件(集成组件、hooks等逻辑)。
- components 组件能够加 fake 数据独立挂载出来, 并能完成非联动性交互。重构完毕后，我们需要生成一个 components-gallery 页面，展示所有可复用组件及其交互。

---

## 附录：反馈与决策记录（重构轮次内新增）

1. 新增 `web/dev` 目录存放开发工具/临时文件；`web/src` 只放业务代码。
2. `tools/clean_web_cache.py`：本轮不做旧缓存迁移，直接清理废弃的 localStorage 旧 key（`kb_theme`/`kb-chat-store`/`kb-docs-store`）。
3. Session-MVVM 的 BUG-003 无需看护：滚动行为维持现状（切 Tab 恢复偏移；切换文档/预览模式 resetKey 归零），`useScrollRestore` 原样平移。
4. **components-gallery 子需求取消**：组件展示与调试改由 Storybook 承接（后续轮次引入）。
5. 实现总结见《重构总结.md》；设计细节见《重构方案.md》《重构方案-反馈.md》。
