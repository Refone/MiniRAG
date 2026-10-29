import type { Meta, StoryObj } from "@storybook/react-vite";
import { QueryProgress } from "./QueryProgress";
import { queryProgress } from "@/stories/fixtures";

const meta = {
  title: "Chat/QueryProgress",
  component: QueryProgress,
  args: { progress: queryProgress.running, open: true },
} satisfies Meta<typeof QueryProgress>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Running: Story = {};

export const Complete: Story = {
  args: { progress: queryProgress.complete },
};

export const Failed: Story = {
  args: { progress: queryProgress.failed },
};

export const Collapsed: Story = {
  args: { open: false },
};
