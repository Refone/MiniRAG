import { useTheme } from "@/theme/ThemeContext";
import { PAGE_TABS } from "@/lib/constants";
import type { PageKey } from "@/types/app";

interface NavBarProps {
  page: PageKey;
  onPageChange: (page: PageKey) => void;
}

export function NavBar({ page, onPageChange }: NavBarProps) {
  const { theme, toggleTheme } = useTheme();

  return (
    <header className="navbar">
      <div className="brand">
        <div className="logo" aria-hidden="true" />
        <div className="title">
          <strong>MiniRAG</strong>
          <span>智能本地知识库 · 对话与文档管理</span>
        </div>
      </div>

      <nav className="tabs" aria-label="页面切换">
        {PAGE_TABS.map((t) => (
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
