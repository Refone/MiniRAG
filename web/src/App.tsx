import { useState } from 'react';
import { NavBar } from '@/components/NavBar';
import { ChatPage } from '@/pages/ChatPage';
import { ImportPage } from '@/pages/ImportPage';
import type { PageKey } from '@/lib/types';

export default function App() {
  const [page, setPage] = useState<PageKey>('chat');

  const handlePageChange = (next: PageKey) => {
    if (next === page) return;
    console.log(`[nav] 切换到「${next === 'chat' ? '对话' : '文件导入'}」`);
    setPage(next);
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-slate-100 text-slate-900 dark:bg-slate-950 dark:text-slate-100">
      <NavBar page={page} onPageChange={handlePageChange} />
      <main className="flex min-h-0 flex-1 p-4">
        {page === 'chat' ? <ChatPage /> : <ImportPage />}
      </main>
    </div>
  );
}
