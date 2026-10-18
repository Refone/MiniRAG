import { useEffect } from "react";
import { normalizeUrl } from "@/lib/chatUtils";

interface ImageLightboxProps {
  /** 当前消息的全部图片（与画廊一致，已剔除加载失败的） */
  images: string[];
  /** 当前预览索引；null 表示关闭 */
  index: number | null;
  /** 正在播放退出淡出过渡（结束后由父组件卸载） */
  closing: boolean;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
}

/**
 * 图片预览浮窗：
 * - 无关闭按钮：点击空白区域即可关闭（带淡出过渡，不突兀）；Esc 关闭；←/→ 切换
 * - 多图时左右出现切换按钮，到达边界时对应按钮隐藏
 * - 计数器贴近图片下方居中显示
 * - 点击图片本身在新标签页打开原图
 */
export function ImageLightbox({
  images,
  index,
  closing,
  onClose,
  onPrev,
  onNext,
}: ImageLightboxProps) {
  useEffect(() => {
    if (index === null) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      } else if (e.key === "ArrowLeft") {
        onPrev();
      } else if (e.key === "ArrowRight") {
        onNext();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, onClose, onPrev, onNext]);

  if (index === null || !images[index]) return null;

  const url = images[index];
  const hasMultiple = images.length > 1;
  const canPrev = hasMultiple && index > 0 && !closing;
  const canNext = hasMultiple && index < images.length - 1 && !closing;

  return (
    <div
      className={`lightbox${closing ? " closing" : ""}`}
      role="dialog"
      aria-modal="true"
      aria-label="图片预览"
      onClick={onClose}
    >
      {canPrev && (
        <button
          type="button"
          className="lightbox-nav lightbox-prev"
          aria-label="上一张"
          title="上一张（←）"
          onClick={(e) => {
            e.stopPropagation();
            onPrev();
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M15 5l-7 7 7 7"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}

      {canNext && (
        <button
          type="button"
          className="lightbox-nav lightbox-next"
          aria-label="下一张"
          title="下一张（→）"
          onClick={(e) => {
            e.stopPropagation();
            onNext();
          }}
        >
          <svg
            width="22"
            height="22"
            viewBox="0 0 24 24"
            fill="none"
            aria-hidden="true"
          >
            <path
              d="M9 5l7 7-7 7"
              stroke="currentColor"
              strokeWidth="2.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </button>
      )}

      <div className="lightbox-body">
        <div className="lightbox-stage">
          <img
            key={url}
            src={normalizeUrl(url)}
            alt="图片预览"
            title="点击在新标签页打开原图"
            referrerPolicy="no-referrer"
            onClick={(e) => {
              e.stopPropagation();
              window.open(
                normalizeUrl(url),
                "_blank",
                "noopener,noreferrer",
              );
            }}
          />
        </div>

        {hasMultiple && (
          <div className="lightbox-bar" onClick={(e) => e.stopPropagation()}>
            <span className="lightbox-count">
              {index + 1} / {images.length}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
