import type { Meta, StoryObj } from "@storybook/react-vite";
import { StatusIcon } from "./StatusIcon";

const meta = {
  title: "Icons/StatusIcon",
  component: StatusIcon,
  args: { kind: "done", size: 16 },
} satisfies Meta<typeof StatusIcon>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Done: Story = {};

export const Failed: Story = { args: { kind: "failed" } };

export const Loading: Story = { args: { kind: "loading" } };

/** 三种状态并排（18px） */
export const AllStates: Story = {
  render: () => (
    <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
      <StatusIcon kind="loading" size={18} />
      <StatusIcon kind="done" size={18} />
      <StatusIcon kind="failed" size={18} />
    </div>
  ),
};
