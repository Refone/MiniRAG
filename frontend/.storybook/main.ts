import type { StorybookConfig } from "@storybook/react-vite";

/**
 * Storybook 配置（组件工作台）：Vite 构建器直接复用 frontend/vite.config.ts，
 * 因此 `@ → src` 别名、React 插件与开发代理都与应用保持一致。
 */
const config: StorybookConfig = {
  // 故事与组件同目录（src 下自动被 tsc 校验）
  stories: ["../src/**/*.stories.@(ts|tsx)"],
  addons: [],
  framework: { name: "@storybook/react-vite", options: {} },
  core: {
    // 匿名遥测默认开启，本项目关闭
    disableTelemetry: true,
  },
};

export default config;
