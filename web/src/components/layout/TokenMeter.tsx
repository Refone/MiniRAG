/**
 * NavBar Token 指示器：
 * - chip：图标 + 「本次访问」标签 + 总量补间数字 + 四模型占比条 + 实时圆点；
 * - 数字随 SSE usage-delta 实时累加（未落账增量叠加在权威快照上），
 *   usage 快照帧到达后回落到权威值，变化过程由 useTweenNumber 补间；
 * - 增量到达 / 权威快照增长时 chip 高亮（420ms 节流），面板打开时改为行闪烁；
 * - 面板：TokenPanel 内容，固定定位在 chip 下方、点击外部 / 关闭按钮收起；
 * - 打开面板静默刷新、加载失败可重试（重试 toast 与 demo 文案一致）。
 */
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { ChevronDownIcon, GaugeIcon } from "@/components/icons/AppIcons";
import { TokenPanel } from "@/components/layout/TokenPanel";
import { useTweenNumber } from "@/hooks/useTweenNumber";
import { TOKEN_KINDS } from "@/lib/constants";
import { useChatStore } from "@/store/chatStore";
import { useDocsStore } from "@/store/docsStore";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import { getBrowserSessionId } from "@/utils/session";
import { formatThousands } from "@/utils/text";
import {
  kindTotal,
  scopeUsage,
  usageKindIncreases,
  withPendingUsage,
} from "@/utils/token";
import type { TokenKind, TokenScope } from "@/types/tokenUsage";

/** 面板最大宽度（demo 契约） */
const PANEL_WIDTH = 360;
/** chip bump 节流（demo 契约 420ms） */
const BUMP_THROTTLE_MS = 420;

export function TokenMeter() {
  const snapshot = useTokenUsageStore((s) => s.snapshot);
  const status = useTokenUsageStore((s) => s.status);
  const lastDelta = useTokenUsageStore((s) => s.lastDelta);
  const pending = useTokenUsageStore((s) => s.pending);
  const sending = useChatStore((s) => s.sending);
  const importing = useDocsStore((s) =>
    s.files.some((f) => f.status === "uploading" || f.status === "processing"),
  );
  const pushToast = useDocsStore((s) => s.pushToast);

  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<TokenScope>("total");
  const [bump, setBump] = useState(false);
  const [flashKinds, setFlashKinds] = useState<TokenKind[]>([]);

  const meterRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevSnapshotRef = useRef(snapshot);
  const lastBumpAtRef = useRef(0);
  const openRef = useRef(open);
  const scopeRef = useRef(scope);
  openRef.current = open;
  scopeRef.current = scope;

  const live = sending || importing;
  /** 展示快照 = 权威快照 + 各通道未落账增量（增量落库前也让数字实时增长） */
  const displaySnapshot = useMemo(
    () =>
      snapshot ? withPendingUsage(snapshot, Object.values(pending)) : null,
    [snapshot, pending],
  );
  const total = displaySnapshot
    ? kindTotal(scopeUsage(displaySnapshot, "total"))
    : 0;
  const unknown = (status === "loading" || status === "error") && !snapshot;
  const chipValue = useTweenNumber(unknown ? null : total);

  const sessionId = snapshot?.session_id ?? getBrowserSessionId();

  /* ---- 首次挂载拉取（store 幂等防重，StrictMode 安全） ---- */
  useEffect(() => {
    const state = useTokenUsageStore.getState();
    if (state.status === "idle") void state.refresh();
  }, []);

  /* ---- chip bump（420ms 节流，增量 / 快照共用） ---- */
  const triggerBump = useCallback(() => {
    const now = Date.now();
    if (now - lastBumpAtRef.current < BUMP_THROTTLE_MS) return;
    lastBumpAtRef.current = now;
    setBump(true);
  }, []);

  /* ---- 面板口径是否命中（行闪烁分支判断用） ---- */
  const scopeMatches = useCallback((source: TokenScope | null) => {
    return scopeRef.current === "total" || scopeRef.current === source;
  }, []);

  /* ---- 单次模型调用增量（SSE usage-delta）：数字已累加，这里负责高亮 ---- */
  useEffect(() => {
    if (!lastDelta) return;
    triggerBump();
    if (!openRef.current) return;
    if (scopeMatches(lastDelta.source)) {
      setFlashKinds((kinds) =>
        kinds.includes(lastDelta.kind) ? kinds : [...kinds, lastDelta.kind],
      );
    }
  }, [lastDelta, triggerBump, scopeMatches]);

  /* ---- 权威快照增长（请求结束的 usage 帧）：面板行闪烁 ---- */
  useEffect(() => {
    const prev = prevSnapshotRef.current;
    prevSnapshotRef.current = snapshot;
    if (!snapshot || !prev) return;
    const increases = usageKindIncreases(
      scopeUsage(snapshot, "total"),
      scopeUsage(prev, "total"),
    );
    const kinds = TOKEN_KINDS.map((k) => k.key).filter(
      (kind) => increases[kind] > 0,
    );
    if (kinds.length === 0) return;

    triggerBump();

    if (!openRef.current) return;
    const source = useTokenUsageStore.getState().lastSource;
    if (scopeMatches(source)) setFlashKinds(kinds);
  }, [snapshot, triggerBump, scopeMatches]);

  /* ---- 面板定位（demo positionPanel） ---- */
  const positionPanel = useCallback(() => {
    const chip = chipRef.current;
    const panel = panelRef.current;
    const nav = meterRef.current?.parentElement;
    if (!chip || !panel || !nav) return;
    const rect = chip.getBoundingClientRect();
    const navRect = nav.getBoundingClientRect();
    const width = Math.min(PANEL_WIDTH, window.innerWidth - 20);
    const left = Math.max(
      10,
      Math.min(rect.right - width, window.innerWidth - width - 10),
    );
    const top = Math.max(rect.bottom, navRect.bottom) + 8;
    panel.style.width = `${width}px`;
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.maxHeight = `${Math.max(240, window.innerHeight - top - 16)}px`;
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    positionPanel();
    window.addEventListener("resize", positionPanel);
    return () => window.removeEventListener("resize", positionPanel);
  }, [open, positionPanel]);

  /* ---- 点击外部关闭（demo pointerdown 语义） ---- */
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (
        meterRef.current &&
        e.target instanceof Node &&
        meterRef.current.contains(e.target)
      ) {
        return;
      }
      setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const handleChipClick = useCallback(() => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    // 后端契约：面板打开时前端刷新；已有数据静默刷新，未加载过则完整加载
    const state = useTokenUsageStore.getState();
    if (state.status === "ready") void state.refresh({ silent: true });
    else if (state.status === "idle") void state.refresh();
  }, [open]);

  const handleRetry = useCallback(() => {
    pushToast("info", "正在重新统计本次访问…");
    void useTokenUsageStore
      .getState()
      .refresh()
      .then((ok) => {
        if (ok) pushToast("success", "Token 统计已恢复");
      });
  }, [pushToast]);

  const sparkRatio = (kind: TokenKind): number => {
    if (!displaySnapshot || total <= 0) return 0;
    return scopeUsage(displaySnapshot, "total")[kind] / total;
  };

  const chipLabel = unknown
    ? "本次访问 Token 统计不可用，点击查看明细"
    : `本次访问 Token 消耗 ${formatThousands(total)}，点击查看明细`;

  return (
    <div className="token-meter" ref={meterRef}>
      <button
        type="button"
        ref={chipRef}
        className={`token-chip${bump ? " is-bump" : ""}${live ? " is-live" : ""}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls="tokenPanel"
        title="浏览器会话 · 查看 Token 消耗明细"
        aria-label={chipLabel}
        onClick={handleChipClick}
        onAnimationEnd={(e) => {
          if (e.animationName === "chip-bump") setBump(false);
        }}
      >
        <span className="token-chip-icon" aria-hidden="true">
          <GaugeIcon />
        </span>
        <span className="token-chip-main">
          <span className="token-chip-label">
            <span className="token-live-dot" aria-hidden="true" />
            本次访问
          </span>
          <span className="token-chip-value">
            <span className="token-num">{chipValue}</span>
            <span className="token-unit">tokens</span>
          </span>
        </span>
        <span className="token-chip-spark" aria-hidden="true">
          {TOKEN_KINDS.map((k) => {
            const ratio = sparkRatio(k.key);
            return (
              <span
                key={k.key}
                data-kind={k.key}
                hidden={ratio <= 0}
                style={{ flex: ratio > 0 ? `${ratio} 1 0%` : "0 0 0" }}
              />
            );
          })}
        </span>
        <ChevronDownIcon className="token-caret" />
      </button>

      {open && (
        <div
          ref={panelRef}
          className="token-panel"
          id="tokenPanel"
          role="dialog"
          aria-label="Token 消耗明细"
        >
          <TokenPanel
            sessionId={sessionId}
            status={status}
            scope={scope}
            snapshot={displaySnapshot}
            live={live}
            flashKinds={flashKinds}
            onScopeChange={setScope}
            onRetry={handleRetry}
            onClose={() => setOpen(false)}
            onFlashEnd={(kind) =>
              setFlashKinds((kinds) => kinds.filter((k) => k !== kind))
            }
          />
        </div>
      )}
    </div>
  );
}
