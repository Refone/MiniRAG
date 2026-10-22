import { useEffect, useLayoutEffect, useRef, type RefObject } from "react";

export interface ScrollRestoreOptions {
  /** 贴底跟随模式: 切回时若此前处于底部附近则滚到底, 否则恢复原位置 */
  followBottom?: boolean;
}

/**
 * Activity 保活下的滚动位置守卫 (测试反馈 #4):
 *
 * 机制说明: 列表 DOM 由 <Activity> 完整保留 (display:none 不销毁), 不做
 * "卸载重挂 + 记录偏移 + 事后滑动" 的方案。但浏览器可能把 display:none
 * 容器的 scrollTop 重置, 因此这里持续被动记录 scrollTop, 并在切回 visible
 * 时于 paint 前 (useLayoutEffect) 恢复 —— DOM 与布局都在, 恢复无可见跳动。
 *
 * followBottom 模式 (会话列表): 同时返回 pinnedRef 供"消息变化时贴底跟随"
 * 逻辑复用 —— 贴底时跟随到底, 用户上翻阅读后切回保持原位置。
 */
export function useScrollRestore<T extends HTMLElement>(
  ref: RefObject<T | null>,
  options: ScrollRestoreOptions = {},
): { pinnedRef: RefObject<boolean> } {
  const { followBottom = false } = options;
  const savedRef = useRef(0);
  const pinnedRef = useRef(followBottom);

  // 被动记录真实滚动位置 (含贴底判定)
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const onScroll = () => {
      savedRef.current = el.scrollTop;
      if (followBottom) {
        pinnedRef.current =
          el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [ref, followBottom]);

  // mount / Activity 切回时于 paint 前恢复 (依赖固定, 语义上只在挂载时执行)
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (followBottom && pinnedRef.current) {
      el.scrollTop = el.scrollHeight;
    } else {
      el.scrollTop = savedRef.current;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { pinnedRef };
}
