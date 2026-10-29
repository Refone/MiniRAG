import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusLog } from "./StatusLog";

const meta = {
  title: "UI/StatusLog",
  component: StatusLog,
  args: {
    lines: [
      { kind: "done", text: "解析 PDF" },
      { kind: "done", text: "OCR 识别" },
      { kind: "running", text: "向量化切块" },
      { kind: "failed", text: "写入向量库" },
    ],
    summary: "导入日志",
    open: true,
    className: "log-details",
    listClassName: "log-list",
  },
  argTypes: { summary: { control: false } },
} satisfies Meta<typeof StatusLog>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Expanded: Story = {};

export const Collapsed: Story = {
  args: { open: false },
};

export const Empty: Story = {
  args: { lines: [], emptyText: "暂无进度" },
};
