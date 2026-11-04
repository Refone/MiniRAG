# 本地 E2E 测试

Playwright + 本地 mock 后端：无需 FastAPI、外部服务与 API key。

```shell
cd frontend
npm i && npx playwright install chromium          # 首次
npm run test:e2e                                  # 全量，约 10s
npx playwright test e2e/chat/query-flow.spec.ts   # 单文件
npm run test:e2e:ui                               # 交互模式（含 trace）
npm run test:e2e:report                           # HTML 报告
```

`config` 的 `webServer` 自动起 mock（4000）与 vite（5174，`VITE_API_BASE` 指向 mock），不影响日常 dev（5173），跑完自动退出。

用例按 `kb_session_id` 隔离；SSE 场景经 `POST /__mock/scenario` 切换，REST 变体用 `page.route`。

## 排障

- 4000 / 5174 被占：关掉占用进程，或改 config 的 `MOCK_PORT` / `APP_PORT`
- 失败：`test-results/` 有截图与 trace，用 `playwright show-trace` 回放

## 校验与 CI

```shell
npm run typecheck:e2e        # 类型检查
npm run build                # 构建
CI=1 npx playwright test     # 模拟 CI（不复用服务）
```

CI 见 `.github/workflows/web-e2e.yml`：`frontend/**` 触发、无 secrets。

mock 契约以 `backend/api/main.py` 与 `frontend/src/lib/sse.ts` 为准，改接口/事件名须同步 `frontend/e2e/mock-server/`，否则回归会假绿。

## 测试产物与磁盘占用

| 路径 | 内容 | 体积（约） | 生命周期 |
| --- | --- | --- | --- |
| `frontend/test-results/` | 每条用例一个目录：`trace.zip`（快照 / 网络 / 控制台 / 失败截图） | 1.3MB/用例；全量运行约 30MB | 每次运行开始时清空重建 |
| `frontend/playwright-report/` | HTML 报告（`test:e2e:report` 打开的那份） | 5MB | 每次运行整体重写 |
| `~/Library/Caches/ms-playwright/` | Chromium 等浏览器二进制 | 570MB | 首次安装后复用，与运行次数无关 |
| `frontend/node_modules/` | 依赖 | 280MB | `npm i` / `npm ci` 时重装 |
| `~/.npm/` | 全局 npm 缓存（非本项目专属） | 通常 GB 级 | 全局共享 |

- `test-results/` 每次运行前由 Playwright 清空、报告目录整体重写：**不会随运行次数累积**，占用上限≈一次完整运行的体量，主要由 trace 决定；不开 trace 时仅 KB 级。
- 两个产物目录已写入 `frontend/.gitignore`，不入库、不污染 `git status`。
- `frontend/e2e/mock-server/` 与 `fixtures/` 是仓库普通文件（几 KB），不是产物；一次性验证脚本放 `var/tmp/`（已 gitignore）。

清理：

```shell
rm -rf frontend/test-results frontend/playwright-report   # 随时可删，下次运行自动重建
```

- 删除后仅丢失上次的回放数据 / 报告；浏览器缓存删掉后需重新 `npx playwright install chromium`。

### trace 何时产生

- `playwright.config.ts` 默认 `trace: retain-on-failure`：只留失败用例，CI 用这个。
- `npm run test:e2e:ui` 带 `--trace on`：每条用例都落 `trace.zip`。UI 模式的 Actions 与快照回放不依赖该文件，去掉 `--trace on` 只是少了可事后 `show-trace` 的独立 trace。
- 单条临时录制：`npx playwright test <spec> --trace on`。
- 回放：`npx playwright show-trace frontend/test-results/<用例目录>/trace.zip`。
