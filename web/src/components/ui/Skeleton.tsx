interface SkeletonProps {
  /** 每行类名（宽度修饰），默认 5 行（w60/w100/w100/w80/w40） */
  widths?: string[];
  /** 容器类名 */
  className?: string;
}

/** 骨架屏行（文档预览加载态） */
export function Skeleton({
  widths = ["w60", "w100", "w100", "w80", "w40"],
  className = "preview-inner",
}: SkeletonProps) {
  return (
    <div className={className}>
      {widths.map((w, i) => (
        <div key={i} className={`skeleton sk-line ${w}`} />
      ))}
    </div>
  );
}
