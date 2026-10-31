import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";

/** 距底部小于该值视为贴底（px）：切回会话时按贴底位置恢复 */
const PIN_THRESHOLD = 80;

export interface ScrollRestoreOptions {
  /** 贴底跟随模式: 切回时若此前处于底部附近则滚到底, 否则恢复原位置 */
  followBottom?: boolean;
  /**
   * 内容身份键。键变化 = 内容已切换 (切换文档 / 切换预览模式):
   * 旧偏移作废, scrollTop 归 0, 之后重新记录; 键不变时挂载 / Activity
   * 切回照常恢复。不传则视为内容恒不变, 保持原"只记录 + 切回恢复"行为。
   */
  resetKey?: unknown;
}

/**
 * Activity 保活下的滚动位置守卫 (测试反馈 #4):
 *
 * 机制说明: 列表 DOM 由 <Activity> 完整保留 (display:none 不销毁), 不做
 * "卸载重挂 + 记录偏移 + 事后滑动" 的方案。但浏览器可能把 display:none
 * 容器的 scrollTop 重置, 因此这里持续被动记录 scrollTop, 并在切回 visible
 * 时于 paint 前 (useLayoutEffect) 恢复 —— DOM 与布局都在, 恢复无可见跳动。
 *
 * resetKey (内容身份): 同一容器在"切换文档 / 切换模式"时内容被替换而节点
 * 保留, 若沿用旧 scrollTop 会随内容漂移, 且浏览器对变短内容的钳制会经
 * scroll 事件反向污染 savedRef, 导致切回旧内容时恢复错误偏移。因此键变化
 * 时偏移归 0, 保证偏移只对当前内容有效 (切 Tab 键不变, 照常恢复)。
 *
 * followBottom 模式 (会话列表): 切回时若此前处于底部附近则滚到底,
 * 否则恢复原位置; 贴底判定只在内部使用。
 */
export function useScrollRestore<T extends HTMLElement>(
  ref: RefObject<T | null>,
  options: ScrollRestoreOptions = {},
): void {
  const { followBottom = false, resetKey } = options;
  const savedRef = useRef(0);
  const pinnedRef = useRef(followBottom);
  /** 上次生效的内容身份键: 首次挂载记为当前键, 不触发复位 */
  const lastKeyRef = useRef(resetKey);

  // 被动记录真实滚动位置 (含贴底判定)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      savedRef.current = el.scrollTop;
      if (followBottom) {
        pinnedRef.current =
          el.scrollHeight - el.scrollTop - el.clientHeight < PIN_THRESHOLD;
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [ref, followBottom]);

  // 内容键变化 → 偏移归 0; 否则 mount / Activity 切回时于 paint 前恢复
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (lastKeyRef.current !== resetKey) {
      // 内容已切换: 丢弃旧偏移, 从头开始 (切换文档/模式 → 偏移归 0)
      lastKeyRef.current = resetKey;
      savedRef.current = 0;
      el.scrollTop = 0;
      if (followBottom) pinnedRef.current = followBottom;
      return;
    }
    if (followBottom && pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    } else {
      el.scrollTop = savedRef.current;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resetKey, followBottom]);
}
