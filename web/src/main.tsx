import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import App from './App';
import { ThemeProvider } from './theme/ThemeContext';
import './styles/global.css';
import './styles/icon.css';

console.log(`[app] 前端启动（mode=${import.meta.env.MODE}）`);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <App />
    </ThemeProvider>
  </StrictMode>,
);
