import { useEffect, useRef, useState } from "react";
import { formatThousands } from "@/utils/text";

/** 补间时长（demo 契约：260ms cubic ease-out） */
const TWEEN_MS = 260;

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * 数字跳变补间（demo 契约，NavBar 与面板共用）：
 * - target 变化时从当前展示值向新值做 260ms cubic ease-out 补间；
 * - target === null 表示统计未知，显示 "—"；
 * - prefers-reduced-motion 时直接跳到目标值。
 */
export function useTweenNumber(target: number | null): string {
  const [display, setDisplay] = useState<number | null>(target);
  const displayRef = useRef<number | null>(target);
  const rafRef = useRef(0);
  const reducedRef = useRef(prefersReducedMotion());

  useEffect(() => {
    if (target === null) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      displayRef.current = null;
      setDisplay(null);
      return;
    }
    const from = displayRef.current;
    if (from === null || from === target || reducedRef.current) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
      displayRef.current = target;
      setDisplay(target);
      return;
    }
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    const start = performance.now();
    const frame = (now: number) => {
      const p = Math.min(1, (now - start) / TWEEN_MS);
      const eased = 1 - Math.pow(1 - p, 3);
      const v = Math.round(from + (target - from) * eased);
      displayRef.current = v;
      setDisplay(v);
      if (p < 1) {
        rafRef.current = requestAnimationFrame(frame);
      } else {
        displayRef.current = target;
        setDisplay(target);
        rafRef.current = 0;
      }
    };
    rafRef.current = requestAnimationFrame(frame);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      rafRef.current = 0;
    };
  }, [target]);

  return display === null ? "—" : formatThousands(display);
}
