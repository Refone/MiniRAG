interface FeaturePanelProps {
  keywords: string;
  abstract: string;
}

/** 特征子页（原 ImportPage features 渲染平移）：关键词 chips + 摘要 */
export function FeaturePanel({ keywords, abstract }: FeaturePanelProps) {
  const kwList = keywords
    .split(/[,，]/)
    .map((k) => k.trim())
    .filter(Boolean);

  return (
    <div className="preview-inner">
      <div className="feature-card">
        <h3 className="feature-title">关键词</h3>
        <div className="feature-chips">
          {kwList.map((k, i) => (
            <span className="kw-chip" key={`${k}-${i}`}>
              {k}
            </span>
          ))}
          {kwList.length === 0 && <span className="doc-type">—</span>}
        </div>
      </div>
      <div className="feature-card">
        <h3 className="feature-title">摘要</h3>
        <p className="feature-abstract">{abstract || "（无摘要）"}</p>
      </div>
    </div>
  );
}
