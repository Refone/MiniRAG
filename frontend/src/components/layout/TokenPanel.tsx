/**
 * Token 明细面板内容（demo 契约：头部 / 三口径 tab / 总计块 / 四模型行 /
 * 空态 / 骨架屏 / 失败重试 / 底部更新时间）。
 * 定位由 TokenMeter 的 .token-panel 容器负责，本组件不参与定位。
 */
import type { FC } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { useTweenNumber } from "@/hooks/useTweenNumber";
import {
  AlertIcon,
  ClockIcon,
  CloseIcon,
  CpuIcon,
  GaugeIcon,
  ImageIcon,
  LayersIcon,
  SortIcon,
} from "@/components/icons/AppIcons";
import {
  TOKEN_KINDS,
  TOKEN_SCOPE_EMPTY,
  TOKEN_SCOPE_LABELS,
  TOKEN_SCOPE_OPTIONS,
} from "@/lib/constants";
import { formatTimeFull } from "@/utils/time";
import { kindTotal, scopeUsage } from "@/utils/token";
import type {
  TokenKind,
  TokenLoadStatus,
  TokenScope,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

const KIND_ICONS: Record<TokenKind, FC<{ className?: string }>> = {
  llm: CpuIcon,
  vlm: ImageIcon,
  embedding: LayersIcon,
  reranker: SortIcon,
};

interface KindRowProps {
  kind: TokenKind;
  label: string;
  model: string;
  value: number;
  pct: number;
  flash: boolean;
  onFlashEnd: () => void;
}

/** 单模型行：数值补间 + 占比 + 进度条 + 行闪烁 */
function KindRow({ kind, label, model, value, pct, flash, onFlashEnd }: KindRowProps) {
  const display = useTweenNumber(value);
  const Icon = KIND_ICONS[kind];
  return (
    <li
      className={`tp-row${flash ? " is-flash" : ""}`}
      data-kind={kind}
      onAnimationEnd={(e) => {
        if (e.animationName === "row-flash") onFlashEnd();
      }}
    >
      <span className="tp-row-icon" aria-hidden="true">
        <Icon />
      </span>
      <span className="tp-row-main">
        <span className="tp-row-name">{label}</span>
        <span className="tp-row-model">{model}</span>
      </span>
      <span className="tp-row-nums">
        <span className="tp-row-val token-num">{display}</span>
        <span className="tp-row-pct">{pct.toFixed(1)}%</span>
      </span>
      <span className="tp-row-bar" aria-hidden="true">
        <span className="tp-row-fill" style={{ width: `${pct.toFixed(2)}%` }} />
      </span>
    </li>
  );
}

export interface TokenPanelProps {
  sessionId: string;
  status: TokenLoadStatus;
  scope: TokenScope;
  snapshot: TokenUsageSnapshot | null;
  /** 查询 / 上传流运行中（实时徽章与「正在更新…」文案） */
  live: boolean;
  /** 本次快照增量命中的模型行（行闪烁） */
  flashKinds: readonly TokenKind[];
  onScopeChange: (scope: TokenScope) => void;
  onRetry: () => void;
  onClose: () => void;
  onFlashEnd: (kind: TokenKind) => void;
  /** 「重置统计」入口：由 TokenMeter 弹确认框并调用 store */
  onResetRequest: () => void;
  /** 查询 / 上传进行中禁止重置（避免落库 flush 把已清零的数据写回） */
  resetDisabled?: boolean;
}

export function TokenPanel({
  sessionId,
  status,
  scope,
  snapshot,
  live,
  flashKinds,
  onScopeChange,
  onRetry,
  onClose,
  onFlashEnd,
  onResetRequest,
  resetDisabled = false,
}: TokenPanelProps) {
  const loading = status === "loading";
  const failed = status === "error" && !snapshot;
  const usage = snapshot ? scopeUsage(snapshot, scope) : null;
  const total = usage ? kindTotal(usage) : 0;
  const totalDisplay = useTweenNumber(loading || failed ? null : total);

  const badge = loading
    ? { text: "统计中", className: "status-processing" }
    : failed
      ? { text: "同步失败", className: "status-error" }
      : live
        ? { text: "实时", className: "status-processing" }
        : { text: "已同步", className: "status-completed" };

  const updatedCopy = loading
    ? "正在统计…"
    : failed
      ? "同步失败"
      : !snapshot || snapshot.total_tokens === 0
        ? "刚刚更新"
        : live
          ? "正在更新…"
          : `${formatTimeFull(snapshot.updated_at)} 更新`;

  return (
    <>
      <div className="tp-head">
        <div className="tp-head-main">
          <strong>Token 消耗</strong>
          <span className="tp-session">浏览器会话 · {sessionId}</span>
        </div>
        <StatusBadge label={badge.text} className={badge.className} />
        <button
          type="button"
          className="tp-close"
          aria-label="关闭 Token 明细"
          title="关闭"
          onClick={onClose}
        >
          <CloseIcon />
        </button>
      </div>

      <div className="tp-tabs-wrap">
        <SegmentedControl
          options={TOKEN_SCOPE_OPTIONS}
          value={scope}
          onChange={onScopeChange}
          ariaLabel="统计范围"
        />
      </div>

      {loading && (
        <div className="tp-skeleton" aria-hidden="true">
          <div className="sk-total">
            <span className="skeleton sk-line w40" />
            <span className="skeleton sk-line w60" />
          </div>
          {TOKEN_KINDS.map((k) => (
            <div className="sk-row" key={k.key}>
              <span className="skeleton sk-dot" />
              <span className="skeleton sk-line" />
              <span className="skeleton sk-line w40" />
            </div>
          ))}
        </div>
      )}

      {failed && (
        <div className="tp-error">
          <AlertIcon />
          <strong>Token 统计加载失败</strong>
          <span>无法获取本次访问的消耗数据，请稍后重试。</span>
          <button type="button" className="btn" onClick={onRetry}>
            重试
          </button>
        </div>
      )}

      {!loading && !failed && usage && (
        <>
          <div className="tp-total">
            <div className="tp-total-row">
              <span className="tp-total-label">{TOKEN_SCOPE_LABELS[scope]}</span>
              <span className="tp-total-value">
                <span className="token-num">{totalDisplay}</span>
                <span className="token-unit">tokens</span>
              </span>
            </div>
            <div className="tp-stack" aria-hidden="true">
              {TOKEN_KINDS.map((k) => {
                const ratio = total > 0 ? usage[k.key] / total : 0;
                return (
                  <span
                    key={k.key}
                    data-kind={k.key}
                    hidden={ratio <= 0}
                    style={{ flex: ratio > 0 ? `${ratio} 1 0%` : "0 0 0" }}
                  />
                );
              })}
            </div>
          </div>

          <ul className="tp-rows">
            {TOKEN_KINDS.map((k) => {
              const value = usage[k.key];
              const pct = total > 0 ? (value / total) * 100 : 0;
              return (
                <KindRow
                  key={k.key}
                  kind={k.key}
                  label={k.label}
                  model={k.model}
                  value={value}
                  pct={pct}
                  flash={flashKinds.includes(k.key)}
                  onFlashEnd={() => onFlashEnd(k.key)}
                />
              );
            })}
          </ul>

          <div className="tp-empty" hidden={total !== 0}>
            <GaugeIcon />
            <span>{TOKEN_SCOPE_EMPTY[scope]}</span>
          </div>
        </>
      )}

      <div className="tp-foot">
        <span className="tp-updated">
          <ClockIcon />
          <span>{updatedCopy}</span>
        </span>
        <span className="tp-foot-actions">
          <span className="tp-foot-note">清空聊天不影响统计</span>
          <button
            type="button"
            className="tp-reset"
            disabled={resetDisabled}
            title={
              resetDisabled
                ? "查询或上传进行中，结束后可重置"
                : "重置本次访问的 Token 统计"
            }
            onClick={onResetRequest}
          >
            重置统计
          </button>
        </span>
      </div>
    </>
  );
}
