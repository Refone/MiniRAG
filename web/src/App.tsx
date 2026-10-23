import { Activity, useEffect, useState } from "react";
import { NavBar } from "@/components/layout/NavBar";
import { ChatPage } from "@/pages/ChatPage";
import { ImportPage } from "@/pages/ImportPage";
import { useChatStore } from "@/store/chatStore";
import { useDocsStore } from "@/store/docsStore";
import { usePreferenceStore } from "@/store/preferenceStore";
import type { PageKey } from "@/types/app";

export default function App() {
  const [page, setPage] = useState<PageKey>("chat");
  const ensureHistoryLoaded = useChatStore((s) => s.ensureHistoryLoaded);
  const ensureDocsLoaded = useDocsStore((s) => s.ensureDocsLoaded);
  const theme = usePreferenceStore((s) => s.theme);
  const toggleTheme = usePreferenceStore((s) => s.toggleTheme);

  // 会话级数据幂等初始化 (StrictMode 双调用安全: store 内有布尔标记, 只拉一次)
  useEffect(() => {
    void ensureHistoryLoaded();
    ensureDocsLoaded();
  }, [ensureHistoryLoaded, ensureDocsLoaded]);

  // 主题 → DOM (preferenceStore 同步水合, 首帧无主题闪烁)
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);

  const handlePageChange = (next: PageKey) => {
    if (next === page) return;
    console.log(`[nav] 切换到「${next === "chat" ? "对话" : "文档管理"}」`);
    setPage(next);
  };

  return (
    <div className="app-shell">
      <NavBar
        page={page}
        onPageChange={handlePageChange}
        theme={theme}
        onToggleTheme={toggleTheme}
      />
      {/* Session-MVVM V0: <Activity> 双保活。隐藏页 display:none 且 effects 销毁,
          state/DOM 保留 —— 滚动/草稿/预览模式等视觉状态切 Tab 不丢失。
          注意: SSE 已上移至 store, 不随 Activity 隐藏断流 (设计文档 §2.2 A2)。 */}
      <main className="app-body">
        <Activity mode={page === "chat" ? "visible" : "hidden"}>
          <ChatPage />
        </Activity>
        <Activity mode={page === "import" ? "visible" : "hidden"}>
          <ImportPage />
        </Activity>
      </main>
    </div>
  );
}
