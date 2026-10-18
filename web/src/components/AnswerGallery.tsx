import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";
import { ImageLightbox } from "@/components/ImageLightbox";
import { normalizeUrl } from "@/lib/chatUtils";
import { layoutGallery, type GalleryRow } from "@/lib/galleryLayout";

interface AnswerGalleryProps {
  images: string[];
}

interface Dims {
  [url: string]: { w: number; h: number };
}

/** 浮窗退出淡出动画时长（与 global.css 的 lightbox-out 保持一致） */
const LIGHTBOX_EXIT_MS = 210;

/**
 * AI 回答的图片画廊：
 * - 紧凑分行排版，不展示 URL
 * - 全部按原始宽高比等比缩放，不裁切、不拉伸
 * - 未加载完成时按占位宽高比占位，加载完成后重排并淡入，避免抖动
 * - 容器宽度 / 视口高度变化时自动重排
 * - 点击图片弹出预览浮窗，支持多图左右切换
 */
export function AnswerGallery({ images }: AnswerGalleryProps) {
  const [dims, setDims] = useState<Dims>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const [containerW, setContainerW] = useState(0);
  const [vh, setVh] = useState(() => window.innerHeight);
  const [viewIndex, setViewIndex] = useState<number | null>(null);
  const [viewClosing, setViewClosing] = useState(false);
  const closeTimerRef = useRef<number | null>(null);
  const boxRef = useRef<HTMLDivElement>(null);

  // 预探测图片原始尺寸（与 <img> 共用浏览器缓存，不产生额外流量）
  useEffect(() => {
    for (const url of images) {
      const probe = new Image();
      probe.onload = () => {
        if (probe.naturalWidth > 0 && probe.naturalHeight > 0) {
          setDims((prev) => ({
            ...prev,
            [url]: { w: probe.naturalWidth, h: probe.naturalHeight },
          }));
        }
      };
      probe.onerror = () => setFailed((prev) => ({ ...prev, [url]: true }));
      probe.src = normalizeUrl(url);
    }
  }, [images]);

  // 容器宽度变化 → 重新布局
  useLayoutEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    setContainerW(Math.round(el.clientWidth));
    const ro = new ResizeObserver(() => {
      setContainerW(Math.round(el.clientWidth));
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // 视口高度变化 → 重算行高上限（30%）
  useEffect(() => {
    const onResize = () => setVh(window.innerHeight);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  /** 可展示的图片（剔除加载失败的），预览浮窗按同一顺序浏览 */
  const visible = useMemo(
    () => images.filter((u) => !failed[u]),
    [images, failed],
  );

  const rows: GalleryRow[] = useMemo(
    () =>
      layoutGallery(
        visible.map((url) => ({
          url,
          naturalW: dims[url]?.w ?? null,
          naturalH: dims[url]?.h ?? null,
        })),
        containerW,
        vh,
      ),
    [visible, dims, containerW, vh],
  );

  const openAt = useCallback(
    (url: string) => {
      const idx = visible.indexOf(url);
      if (idx < 0) return;
      // 若正处于退出过渡中，取消待执行的卸载，直接切换目标图片
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
        closeTimerRef.current = null;
      }
      setViewClosing(false);
      setViewIndex(idx);
    },
    [visible],
  );

  /** 先播放淡出过渡，动画结束后再卸载浮窗 */
  const closeView = useCallback(() => {
    if (viewClosing) return;
    setViewClosing(true);
    closeTimerRef.current = window.setTimeout(() => {
      closeTimerRef.current = null;
      setViewClosing(false);
      setViewIndex(null);
    }, LIGHTBOX_EXIT_MS);
  }, [viewClosing]);

  const showPrev = useCallback(() => {
    if (viewClosing) return;
    setViewIndex((i) => (i === null ? i : Math.max(0, i - 1)));
  }, [viewClosing]);

  const showNext = useCallback(() => {
    if (viewClosing) return;
    setViewIndex((i) =>
      i === null ? i : Math.min(visible.length - 1, i + 1),
    );
  }, [viewClosing, visible.length]);

  // 卸载时清理待执行的关闭定时器
  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    },
    [],
  );

  const onImgKeyDown = (url: string) => (e: ReactKeyboardEvent<HTMLImageElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openAt(url);
    }
  };

  return (
    <div className="answer-gallery" ref={boxRef}>
      {rows.map((row, ri) => (
        <div
          key={ri}
          className="gallery-row"
          style={{ height: row.height }}
        >
          {row.items.map((item, ii) => (
            <img
              key={`${ri}-${ii}`}
              src={normalizeUrl(item.url)}
              alt="参考图片"
              loading="lazy"
              referrerPolicy="no-referrer"
              className={item.capped ? "capped" : undefined}
              style={{
                width: item.width,
                height: item.height,
                opacity: dims[item.url] ? 1 : 0,
              }}
              onClick={() => openAt(item.url)}
              onKeyDown={onImgKeyDown(item.url)}
              role="button"
              tabIndex={0}
              aria-label="查看大图"
              onError={() =>
                setFailed((prev) => ({ ...prev, [item.url]: true }))
              }
            />
          ))}
        </div>
      ))}

      <ImageLightbox
        images={visible}
        index={viewIndex}
        closing={viewClosing}
        onClose={closeView}
        onPrev={showPrev}
        onNext={showNext}
      />
    </div>
  );
}
