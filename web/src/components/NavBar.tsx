import { useTheme } from "@/theme/ThemeContext";
import type { PageKey } from "@/lib/types";

interface NavBarProps {
  page: PageKey;
  onPageChange: (page: PageKey) => void;
}

const TABS: { key: PageKey; label: string; icon: string }[] = [
  { key: "chat", label: "对话", icon: "💬" },
  { key: "import", label: "文件导入", icon: "📄" },
];

export function NavBar({ page, onPageChange }: NavBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="navbar">
      <div className="brand">
        <div className="logo" aria-hidden="true" />
        <div className="title">
          <strong>MiniRAG</strong>
          <span>智能本地知识库 · 对话与文档导入</span>
        </div>
      </div>

      <nav className="tabs" aria-label="页面切换">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`tab${page === t.key ? " active" : ""}`}
            aria-current={page === t.key ? "page" : undefined}
            onClick={() => onPageChange(t.key)}
          >
            <span className="tab-icon">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <button
        type="button"
        className="theme-toggle"
        onClick={toggleTheme}
        title={theme === "light" ? "切换到深色模式" : "切换到浅色模式"}
        aria-label={theme === "light" ? "切换到深色模式" : "切换到浅色模式"}
      >
        <span className="theme-toggle-icon">
          {theme === "light" ? "🌙" : "☀️"}
        </span>
        <span className="theme-toggle-label">
          {theme === "light" ? "深色" : "浅色"}
        </span>
      </button>
    </header>
  );
}
