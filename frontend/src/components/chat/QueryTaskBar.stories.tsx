import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryTaskBar } from "./QueryTaskBar";
import { queryProgress, queryTask } from "@/stories/fixtures";

const meta = {
  title: "Chat/QueryTaskBar",
  component: QueryTaskBar,
  args: { task: queryTask, onDismiss: () => {} },
} satisfies Meta<typeof QueryTaskBar>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 运行中：右侧没有关闭按钮 */
export const Running: Story = {};

/** 终态：可关闭 */
export const Complete: Story = {
  args: { task: { id: "task-query-2", progress: queryProgress.complete } },
};

export const Failed: Story = {
  args: { task: { id: "task-query-3", progress: queryProgress.failed } },
};
