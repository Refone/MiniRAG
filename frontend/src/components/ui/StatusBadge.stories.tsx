import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusBadge } from "./StatusBadge";

const meta = {
  title: "UI/StatusBadge",
  component: StatusBadge,
  args: { label: "已完成", className: "status-completed" },
} satisfies Meta<typeof StatusBadge>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Completed: Story = {};

export const Processing: Story = {
  args: { label: "处理中", className: "status-processing" },
};

export const Pending: Story = {
  args: { label: "排队中", className: "status-pending" },
};

export const Failed: Story = {
  args: { label: "失败", className: "status-error" },
};
