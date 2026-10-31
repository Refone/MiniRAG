/**
 * NavBar Token 指示器（demo 契约）：
 * - chip：图标 + 「本次访问」标签 + 总量补间数字 + 四模型占比条 + 实时圆点；
 * - 快照增量时 chip 边框 bump（420ms 节流）、面板关闭时数字下方浮动 +N 增量；
 * - 面板：TokenPanel 内容，固定定位在 chip 下方、点击外部 / 关闭按钮收起；
 * - 打开面板静默刷新、加载失败可重试（重试 toast 与 demo 文案一致）。
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { ChevronDownIcon, GaugeIcon } from "@/components/icons/AppIcons";
import { TokenPanel } from "@/components/layout/TokenPanel";
import { useTweenNumber } from "@/hooks/useTweenNumber";
import { TOKEN_KINDS } from "@/lib/constants";
import { useChatStore } from "@/store/chatStore";
import { useDocsStore } from "@/store/docsStore";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import { getBrowserSessionId } from "@/utils/session";
import { formatThousands } from "@/utils/text";
import { kindTotal, scopeUsage, usageIncreases } from "@/utils/token";
import type { TokenKind, TokenScope } from "@/types/tokenUsage";

/** 面板最大宽度（demo 契约） */
const PANEL_WIDTH = 360;
/** chip bump 节流（demo 契约 420ms） */
const BUMP_THROTTLE_MS = 420;

const KIND_LABELS: Record<TokenKind, string> = Object.fromEntries(
  TOKEN_KINDS.map((k) => [k.key, k.label]),
) as Record<TokenKind, string>;

export function TokenMeter() {
  const snapshot = useTokenUsageStore((s) => s.snapshot);
  const status = useTokenUsageStore((s) => s.status);
  const sending = useChatStore((s) => s.sending);
  const importing = useDocsStore((s) =>
    s.files.some((f) => f.status === "uploading" || f.status === "processing"),
  );
  const pushToast = useDocsStore((s) => s.pushToast);

  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<TokenScope>("total");
  const [bump, setBump] = useState(false);
  const [delta, setDelta] = useState<{
    text: string;
    kind: TokenKind | null;
  } | null>(null);
  const [flashKinds, setFlashKinds] = useState<TokenKind[]>([]);

  const meterRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevSnapshotRef = useRef(snapshot);
  const lastBumpAtRef = useRef(0);
  const deltaSeqRef = useRef(0);
  const openRef = useRef(open);
  const scopeRef = useRef(scope);
  openRef.current = open;
  scopeRef.current = scope;

  const live = sending || importing;
  const total = snapshot ? kindTotal(scopeUsage(snapshot, "total")) : 0;
  const unknown = (status === "loading" || status === "error") && !snapshot;
  const chipValue = useTweenNumber(unknown ? null : total);

  const sessionId = snapshot?.session_id ?? getBrowserSessionId();

  /* ---- 首次挂载拉取（store 幂等防重，StrictMode 安全） ---- */
  useEffect(() => {
    const state = useTokenUsageStore.getState();
    if (state.status === "idle") void state.refresh();
  }, []);

  /* ---- 快照增量 → bump / 行闪烁 / 浮动增量（demo applyAdd 语义） ---- */
  useEffect(() => {
    const prev = prevSnapshotRef.current;
    prevSnapshotRef.current = snapshot;
    if (!snapshot || !prev) return;
    const { kinds, amount } = usageIncreases(
      scopeUsage(snapshot, "total"),
      scopeUsage(prev, "total"),
    );
    if (amount <= 0) return;

    const now = Date.now();
    if (now - lastBumpAtRef.current >= BUMP_THROTTLE_MS) {
      lastBumpAtRef.current = now;
      setBump(true);
    }

    if (openRef.current) {
      const source = useTokenUsageStore.getState().lastSource;
      if (scopeRef.current === "total" || scopeRef.current === source) {
        setFlashKinds(kinds);
      }
    } else {
      deltaSeqRef.current += 1;
      setDelta(
        kinds.length === 1
          ? {
              text: `+${formatThousands(amount)} ${KIND_LABELS[kinds[0]]}`,
              kind: kinds[0],
            }
          : { text: `+${formatThousands(amount)} tokens`, kind: null },
      );
    }
  }, [snapshot]);

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
    if (!snapshot || total <= 0) return 0;
    return scopeUsage(snapshot, "total")[kind] / total;
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
            snapshot={snapshot}
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

      <span
        key={deltaSeqRef.current}
        className={`token-delta${delta ? " show" : ""}`}
        aria-hidden="true"
        style={{
          color: delta?.kind
            ? `var(--c-${delta.kind})`
            : "var(--accent)",
        }}
        onAnimationEnd={(e) => {
          if (e.animationName === "delta-float") setDelta(null);
        }}
      >
        {delta?.text ?? ""}
      </span>
    </div>
  );
}
