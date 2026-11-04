import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChunkCard } from "./ChunkCard";
import { chunks } from "@/stories/fixtures";

const meta = {
  title: "Docs/ChunkCard",
  component: ChunkCard,
  args: { index: 0, chunk: chunks[0], showSplit: true },
} satisfies Meta<typeof ChunkCard>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const HeadingLevel3: Story = {
  args: { index: 2, chunk: chunks[2] },
};

/** 最后一块：不渲染 split 标记 */
export const LastChunk: Story = {
  args: { index: 3, chunk: chunks[3], showSplit: false },
};
