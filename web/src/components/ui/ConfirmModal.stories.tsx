import type { Meta, StoryObj } from "@storybook/react-vite";
import { ConfirmModal } from "./ConfirmModal";

const meta = {
  title: "UI/ConfirmModal",
  component: ConfirmModal,
  args: {
    title: "删除文档？",
    children: "删除后不可恢复，确认删除《MiniRAG 使用手册.pdf》吗？",
    onConfirm: () => {},
    onCancel: () => {},
  },
  argTypes: { children: { control: false } },
} satisfies Meta<typeof ConfirmModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

/** 确认按钮忙碌态 */
export const Busy: Story = {
  args: { busy: true },
};
