import { useState } from "react";
import { NavBar } from "@/components/NavBar";
import { ChatPage } from "@/pages/ChatPage";
import { ImportPage } from "@/pages/ImportPage";
import type { PageKey } from "@/lib/types";

export default function App() {
  const [page, setPage] = useState<PageKey>("chat");

  const handlePageChange = (next: PageKey) => {
    if (next === page) return;
    console.log(`[nav] 切换到「${next === "chat" ? "对话" : "文件导入"}」`);
    setPage(next);
  };

  return (
    <div className="app-shell">
      <NavBar page={page} onPageChange={handlePageChange} />
      <main className="app-body">
        {page === "chat" ? <ChatPage /> : <ImportPage />}
      </main>
    </div>
  );
}
