/**
 * 偏好持久层 Store（按存储方式分层：localStorage · zustand persist）
 *
 * - 汇聚全部跨刷新保留的用户偏好：theme / enableWebSearch / enableHyde / previewMode；
 * - 全新 key 起步、不读旧数据（反馈第 3 条：旧缓存不迁移，由 web/dev/clean_cache.py 清理）；
 * - localStorage 同步读写 → persist 同步水合，首帧主题无闪烁（原 ThemeContext 语义）。
 */
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { PREFERENCE_STORE_NAME } from "@/lib/constants";
import type { PreviewMode } from "@/types/docs";

export type Theme = "light" | "dark";

/**
 * 首次无存储时的初始主题：跟随系统偏好（原 ThemeContext 语义）。
 * persist 同步水合会覆盖初始值，因此仅"从未存储过"时生效。
 */
function getInitialTheme(): Theme {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

interface PreferenceState {
  theme: Theme;
  enableWebSearch: boolean;
  enableHyde: boolean;
  previewMode: PreviewMode;

  toggleTheme: () => void;
  setEnableWebSearch: (v: boolean) => void;
  setEnableHyde: (v: boolean) => void;
  setPreviewMode: (v: PreviewMode) => void;
}

export const usePreferenceStore = create<PreferenceState>()(
  persist(
    (set) => ({
      theme: getInitialTheme(),
      enableWebSearch: true,
      enableHyde: true,
      previewMode: "markdown",

      toggleTheme: () =>
        set((s) => ({ theme: s.theme === "light" ? "dark" : "light" })),
      setEnableWebSearch: (v) => set({ enableWebSearch: v }),
      setEnableHyde: (v) => set({ enableHyde: v }),
      setPreviewMode: (v) => set({ previewMode: v }),
    }),
    { name: PREFERENCE_STORE_NAME, version: 1 },
  ),
);
