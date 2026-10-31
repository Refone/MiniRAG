/**
 * NavBar Token 指示器（demo 契约）：
 * - chip：图标 + 「本次访问」标签 + 总量补间数字 + 四模型占比条 + 实时圆点；
 * - 气泡（面板关闭时）：单次模型调用结束（SSE usage-delta）→ 立即弹「+N 模型」
 *   彩色气泡；请求结束（SSE usage 快照帧）→ 弹「+N tokens」总气泡；
 *   多个气泡按到达顺序排队逐个浮现（每个 1.1s），每次弹泡伴随 chip bump；
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
import { kindTotal, scopeUsage, usageKindIncreases } from "@/utils/token";
import type { TokenKind, TokenScope } from "@/types/tokenUsage";

/** 面板最大宽度（demo 契约） */
const PANEL_WIDTH = 360;
/** chip bump 节流（demo 契约 420ms） */
const BUMP_THROTTLE_MS = 420;

const KIND_LABELS: Record<TokenKind, string> = Object.fromEntries(
  TOKEN_KINDS.map((k) => [k.key, k.label]),
) as Record<TokenKind, string>;

/** 气泡队列单元：kind 为 null 表示请求结束的总气泡（accent 色） */
interface DeltaBeat {
  id: number;
  text: string;
  kind: TokenKind | null;
}

export function TokenMeter() {
  const snapshot = useTokenUsageStore((s) => s.snapshot);
  const status = useTokenUsageStore((s) => s.status);
  const lastDelta = useTokenUsageStore((s) => s.lastDelta);
  const sending = useChatStore((s) => s.sending);
  const importing = useDocsStore((s) =>
    s.files.some((f) => f.status === "uploading" || f.status === "processing"),
  );
  const pushToast = useDocsStore((s) => s.pushToast);

  const [open, setOpen] = useState(false);
  const [scope, setScope] = useState<TokenScope>("total");
  const [bump, setBump] = useState(false);
  const [beats, setBeats] = useState<DeltaBeat[]>([]);
  const [flashKinds, setFlashKinds] = useState<TokenKind[]>([]);

  const meterRef = useRef<HTMLDivElement>(null);
  const chipRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const prevSnapshotRef = useRef(snapshot);
  const lastBumpAtRef = useRef(0);
  const beatSeqRef = useRef(0);
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

  /* ---- chip bump（420ms 节流，气泡 / 快照共用） ---- */
  const triggerBump = useCallback(() => {
    const now = Date.now();
    if (now - lastBumpAtRef.current < BUMP_THROTTLE_MS) return;
    lastBumpAtRef.current = now;
    setBump(true);
  }, []);

  /* ---- 面板口径是否命中（行闪烁 / 气泡分支判断用） ---- */
  const scopeMatches = useCallback((source: TokenScope | null) => {
    return scopeRef.current === "total" || scopeRef.current === source;
  }, []);

  /* ---- 单次模型调用增量（SSE usage-delta）：立即弹「+N 模型」气泡 ---- */
  useEffect(() => {
    if (!lastDelta) return;
    triggerBump();
    if (openRef.current) {
      if (scopeMatches(lastDelta.source)) {
        setFlashKinds((kinds) =>
          kinds.includes(lastDelta.kind) ? kinds : [...kinds, lastDelta.kind],
        );
      }
      return;
    }
    beatSeqRef.current += 1;
    setBeats((queue) => [
      ...queue,
      {
        id: beatSeqRef.current,
        text: `+${formatThousands(lastDelta.tokens)} ${KIND_LABELS[lastDelta.kind]}`,
        kind: lastDelta.kind,
      },
    ]);
  }, [lastDelta, triggerBump, scopeMatches]);

  /* ---- 快照增量（请求结束的权威帧）：弹「+N tokens」总气泡 + 行闪烁 ---- */
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
    const totalDelta = kinds.reduce((sum, kind) => sum + increases[kind], 0);
    if (totalDelta <= 0) return;

    triggerBump();

    if (openRef.current) {
      const source = useTokenUsageStore.getState().lastSource;
      if (scopeMatches(source)) setFlashKinds(kinds);
      return;
    }

    beatSeqRef.current += 1;
    setBeats((queue) => [
      ...queue,
      {
        id: beatSeqRef.current,
        text: `+${formatThousands(totalDelta)} tokens`,
        kind: null,
      },
    ]);
  }, [snapshot, triggerBump, scopeMatches]);

  /* ---- 气泡出队: 当前气泡动画结束后播放下一个 (同时 bump) ---- */
  const handleBeatEnd = useCallback(() => {
    setBeats((queue) => queue.slice(1));
    triggerBump();
  }, [triggerBump]);

  /* ---- 面板打开即中止气泡队列 (改行闪烁呈现) ---- */
  useEffect(() => {
    if (!open) return;
    setBeats((queue) => (queue.length > 0 ? [] : queue));
  }, [open]);

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

      {beats.length > 0 && (
        <span
          key={beats[0].id}
          className="token-delta show"
          aria-hidden="true"
          style={{
            color: beats[0].kind
              ? `var(--c-${beats[0].kind})`
              : "var(--accent)",
          }}
          onAnimationEnd={(e) => {
            if (e.animationName === "delta-float") handleBeatEnd();
          }}
        >
          {beats[0].text}
        </span>
      )}
    </div>
  );
}
