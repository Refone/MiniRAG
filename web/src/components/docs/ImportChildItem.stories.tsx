import type { Meta, StoryObj } from "@storybook/react-vite";
import { ImportChildItem } from "./ImportChildItem";
import { importChild } from "@/stories/fixtures";

const meta = {
  title: "Docs/ImportChildItem",
  component: ImportChildItem,
  args: { child: importChild },
  decorators: [
    (Story) => (
      <ul className="child-tree">
        <Story />
      </ul>
    ),
  ],
} satisfies Meta<typeof ImportChildItem>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Processing: Story = {};

export const Complete: Story = {
  args: {
    child: {
      ...importChild,
      status: "complete",
      stoppedAt: Date.now(),
      done: ["解析 Markdown", "切块", "写入向量库"],
      running: [],
    },
  },
};

export const Failed: Story = {
  args: {
    child: {
      ...importChild,
      status: "failed",
      stoppedAt: Date.now(),
      done: ["解析 Markdown"],
      running: [],
      failed: ["切块"],
      error: "模型调用超时",
    },
  },
};

export const Pending: Story = {
  args: {
    child: { ...importChild, status: "pending", startedAt: null, done: [], running: [] },
  },
};

export const Interrupted: Story = {
  args: {
    child: { ...importChild, status: "interrupted", stoppedAt: null },
  },
};
