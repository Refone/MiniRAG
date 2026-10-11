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
    <header className="flex shrink-0 flex-wrap items-center gap-3 border-b border-slate-200 bg-white px-5 py-3 dark:border-slate-800 dark:bg-slate-900">
      <div className="flex min-w-0 items-center gap-2.5">
        <div
          aria-hidden="true"
          className="h-9 w-9 shrink-0 rounded-lg bg-gradient-to-br from-indigo-500 to-violet-500 shadow"
        />
        <div className="flex min-w-0 flex-col leading-tight">
          <strong className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
            MiniRAG
          </strong>
          <span className="mt-0.5 truncate text-xs text-slate-500 dark:text-slate-400">
            智能本地知识库 · 对话与文档导入
          </span>
        </div>
      </div>

      <nav className="ml-auto flex gap-1.5" aria-label="页面切换">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`inline-flex items-center gap-1.5 rounded-full border px-3.5 py-2 text-[13px] transition ${
              page === t.key
                ? "border-transparent bg-indigo-600 text-white"
                : "border-slate-200 bg-white text-slate-500 hover:border-indigo-400 hover:text-slate-900 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400 dark:hover:text-slate-100"
            }`}
            aria-current={page === t.key ? "page" : undefined}
            onClick={() => onPageChange(t.key)}
          >
            <span className="text-sm leading-none">{t.icon}</span>
            {t.label}
          </button>
        ))}
      </nav>

      <button
        type="button"
        className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white px-3 py-2 text-[13px] text-slate-700 transition hover:border-indigo-400 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
        onClick={toggleTheme}
        title={theme === "light" ? "切换到深色模式" : "切换到浅色模式"}
        aria-label={theme === "light" ? "切换到深色模式" : "切换到浅色模式"}
      >
        <span className="text-sm leading-none">
          {theme === "light" ? "🌙" : "☀️"}
        </span>
        <span className="hidden sm:inline">
          {theme === "light" ? "深色" : "浅色"}
        </span>
      </button>
    </header>
  );
}
