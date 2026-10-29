import type { Meta, StoryObj } from "@storybook/react-vite";
import { MessageBubble } from "./MessageBubble";
import { chatMessages } from "@/stories/fixtures";

const meta = {
  title: "Chat/MessageBubble",
  component: MessageBubble,
  args: { message: chatMessages.user },
} satisfies Meta<typeof MessageBubble>;

export default meta;
type Story = StoryObj<typeof meta>;

export const User: Story = {};

export const BotAnswer: Story = {
  args: { message: chatMessages.botAnswer },
};

export const Typing: Story = {
  args: { message: chatMessages.botTyping },
};

/** 流式输出：未闭合的图片语法先显示占位 */
export const Streaming: Story = {
  args: { message: chatMessages.botStreaming },
};

export const Failed: Story = {
  args: { message: chatMessages.botError },
};

/** 已完成但答案为空 */
export const EmptyAnswer: Story = {
  args: { message: chatMessages.botEmpty },
};
