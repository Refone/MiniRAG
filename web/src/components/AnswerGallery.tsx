import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { normalizeUrl } from "@/lib/chatUtils";
import { layoutGallery, type GalleryRow } from "@/lib/galleryLayout";

interface AnswerGalleryProps {
  images: string[];
}

interface Dims {
  [url: string]: { w: number; h: number };
}

/**
 * AI 回答的图片画廊：
 * - 紧凑分行排版，不展示 URL
 * - 全部按原始宽高比等比缩放，不裁切、不拉伸
 * - 未加载完成时按占位宽高比占位，加载完成后重排并淡入，避免抖动
 * - 容器宽度 / 视口高度变化时自动重排
 */
export function AnswerGallery({ images }: AnswerGalleryProps) {
  const [dims, setDims] = useState<Dims>({});
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const [containerW, setContainerW] = useState(0);
  const [vh, setVh] = useState(() => window.innerHeight);
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

  const rows: GalleryRow[] = useMemo(
    () =>
      layoutGallery(
        images
          .filter((u) => !failed[u])
          .map((url) => ({
            url,
            naturalW: dims[url]?.w ?? null,
            naturalH: dims[url]?.h ?? null,
          })),
        containerW,
        vh,
      ),
    [images, dims, failed, containerW, vh],
  );

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
              onError={() =>
                setFailed((prev) => ({ ...prev, [item.url]: true }))
              }
            />
          ))}
        </div>
      ))}
    </div>
  );
}
