import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type RefObject,
} from "react";
import type { DocsChunkItem } from "@/types/docs";

interface ChunkRailProps {
  /** 预览滚动容器（rail 监听其滚动以高亮当前 chunk） */
  containerRef: RefObject<HTMLDivElement | null>;
  chunks: DocsChunkItem[];
  /** 内容身份键（`${selectedId}:${previewMode}`）：变化 → 高亮归 0 */
  resetKey: string;
  /** 是否渲染（chunks 模式且有选中文档时显示） */
  hidden?: boolean;
}

/**
 * ChunkRail（文档管理页 ChunkRail 逻辑平移，内部自持全部状态）：
 * 长度分布条 + 悬停 tip + 滚动高亮 + 点击平滑定位。
 * - resetKey 变化 → railActive 归 0（保留 prevSelKeyRef 守卫：仅真正切换
 *   文档/模式时重置，切回 Tab 保持原高亮，与恢复的滚动位置一致）
 * - 挂载 / Activity 切回时 useLayoutEffect 重算高亮（原语义）
 */
export function ChunkRail({
  containerRef,
  chunks,
  resetKey,
  hidden = false,
}: ChunkRailProps) {
  const [railActive, setRailActive] = useState(-1);
  const railFrameRef = useRef(0);
  const [railTip, setRailTip] = useState<{
    text: string;
    left: number;
    top: number;
  } | null>(null);

  const railSizes = useMemo(
    () => chunks.map((c) => c.content.length),
    [chunks],
  );
  const railMax = useMemo(
    () => railSizes.reduce((m, n) => Math.max(m, n), 0) || 1,
    [railSizes],
  );

  // Activity 切回后重算高亮（滚动位置恢复后保持一致）
  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const cards = container.querySelectorAll<HTMLElement>("[data-chunk-index]");
    if (!cards.length) return;
    const containerTop = container.getBoundingClientRect().top;
    let index = 0;
    cards.forEach((el, i) => {
      if (el.getBoundingClientRect().top <= containerTop + 8) index = i;
    });
    setRailActive(index);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // 切换文档/预览模式时重置高亮（守卫：切回 Tab 不重置）
  const prevSelKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (prevSelKeyRef.current !== resetKey) {
      prevSelKeyRef.current = resetKey;
      setRailActive(-1);
    }
  }, [resetKey]);

  const onPreviewScroll = useCallback(() => {
    setRailTip(null);
    if (!railSizes.length || railFrameRef.current) return;
    railFrameRef.current = window.requestAnimationFrame(() => {
      railFrameRef.current = 0;
      const container = containerRef.current;
      if (!container) return;
      const cards = container.querySelectorAll<HTMLElement>(
        "[data-chunk-index]",
      );
      if (!cards.length) return;
      const containerTop = container.getBoundingClientRect().top;
      let index = 0;
      cards.forEach((el, i) => {
        if (el.getBoundingClientRect().top <= containerTop + 8) index = i;
      });
      setRailActive(index);
    });
  }, [railSizes, containerRef]);

  // 监听预览容器滚动（替代原 onScroll prop）
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    container.addEventListener("scroll", onPreviewScroll, { passive: true });
    return () => container.removeEventListener("scroll", onPreviewScroll);
  }, [containerRef, onPreviewScroll]);

  const scrollToChunk = useCallback(
    (index: number) => {
      const container = containerRef.current;
      if (!container) return;
      const el = container.querySelector<HTMLElement>(
        `[data-chunk-index="${index}"]`,
      );
      if (!el) return;
      const top =
        el.getBoundingClientRect().top -
        container.getBoundingClientRect().top +
        container.scrollTop -
        12;
      container.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
      setRailActive(index);
    },
    [containerRef],
  );

  const showRailTip = useCallback(
    (index: number, e: React.MouseEvent<HTMLButtonElement>) => {
      const n = railSizes[index] ?? 0;
      const r = (e.target as HTMLElement).getBoundingClientRect();
      setRailTip({
        text: `Chunk ${index + 1} · ${n.toLocaleString("zh-CN")} chars`,
        left: r.left,
        top: r.top + r.height / 2,
      });
    },
    [railSizes],
  );

  return (
    <>
      <aside
        className="chunk-rail"
        aria-label="Chunk 长度分布"
        hidden={hidden}
      >
        <div className="rail-caption">total: {railSizes.length}</div>
        {railSizes.map((n, i) => {
          const pct = Math.max(5, (n / railMax) * 100);
          return (
            <div className="rail-row" key={i}>
              <button
                className={`rail-bar${railActive === i ? " active" : ""}`}
                type="button"
                data-index={i}
                aria-label={`Chunk ${i + 1}, ${n} chars`}
                style={{ width: `${pct.toFixed(2)}%` }}
                onClick={() => scrollToChunk(i)}
                onMouseEnter={(e) => showRailTip(i, e)}
                onMouseLeave={() => setRailTip(null)}
              />
              <span className="rail-num">{i + 1}</span>
            </div>
          );
        })}
      </aside>

      {railTip && (
        <div
          className="rail-tip"
          role="tooltip"
          style={{ left: railTip.left, top: railTip.top }}
        >
          {railTip.text}
        </div>
      )}
    </>
  );
}
