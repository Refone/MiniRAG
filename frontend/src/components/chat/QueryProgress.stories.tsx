import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryProgress } from "./QueryProgress";
import { queryProgress } from "@/stories/fixtures";

const meta = {
  title: "Chat/QueryProgress",
  component: QueryProgress,
  args: { progress: queryProgress.running },
} satisfies Meta<typeof QueryProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 默认收起：应用内始终以该状态出现，详情由用户点击摘要展开 */
export const Running: Story = {};

/** 展开态（仅预览：应用内不传 open，展开由用户控制） */
export const RunningOpen: Story = {
  args: { open: true },
};

export const Complete: Story = {
  args: { progress: queryProgress.complete },
};

export const Failed: Story = {
  args: { progress: queryProgress.failed },
};
