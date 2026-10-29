import type { Decorator, Preview } from "@storybook/react-vite";
import "../src/styles/index.css";

/** 主题装饰器：工具栏 light/dark → html[data-theme]，与应用同一套 tokens */
const withTheme: Decorator = (Story, context) => {
  document.documentElement.dataset.theme =
    context.globals.theme === "dark" ? "dark" : "light";
  return (
    <div
      style={{
        minHeight: "100vh",
        padding: 24,
        background: "var(--bg)",
        color: "var(--text)",
        fontFamily: "var(--font-sans)",
      }}
    >
      <Story />
    </div>
  );
};

const preview: Preview = {
  decorators: [withTheme],
  globalTypes: {
    theme: {
      description: "主题",
      toolbar: {
        icon: "paintbrush",
        items: ["light", "dark"],
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: { theme: "light" },
  parameters: { layout: "fullscreen" },
};

export default preview;
