import type { Meta, StoryObj } from "@storybook/react-vite";
import { Toast } from "./Toast";

const meta = {
  title: "UI/Toast",
  component: Toast,
  args: {
    toasts: [
      { id: 1, kind: "success", text: "文档导入完成" },
      { id: 2, kind: "error", text: "导入失败：文件解析异常" },
      { id: 3, kind: "info", text: "文档列表已刷新" },
    ],
  },
} satisfies Meta<typeof Toast>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Stack: Story = {};
