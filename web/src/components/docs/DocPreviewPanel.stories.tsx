import { createRef } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { DocPreviewPanel } from "./DocPreviewPanel";
import { docsDetail } from "@/stories/fixtures";

/** 面板自己把该 ref 挂到 .preview-scroll 上，ChunkRail 复用它 */
const scrollRef = createRef<HTMLDivElement>();

const meta = {
  title: "Docs/DocPreviewPanel",
  component: DocPreviewPanel,
  args: {
    title: docsDetail.title,
    hasSelection: true,
    detail: docsDetail,
    loading: false,
    mode: "markdown",
    onModeChange: () => {},
    scrollRef,
    resetKey: "doc_1001:markdown",
  },
  render: (args) => (
    <div style={{ height: 640, display: "flex" }}>
      <DocPreviewPanel {...args} />
    </div>
  ),
} satisfies Meta<typeof DocPreviewPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Markdown: Story = {};

export const Chunks: Story = {
  args: { mode: "chunks", resetKey: "doc_1001:chunks" },
};

export const Features: Story = {
  args: { mode: "features", resetKey: "doc_1001:features" },
};

export const Loading: Story = {
  args: { loading: true },
};

/** 未选中文档：空态 + 分段开关禁用 */
export const Empty: Story = {
  args: {
    title: "未选择文档",
    hasSelection: false,
    detail: null,
    resetKey: "none:markdown",
  },
};
