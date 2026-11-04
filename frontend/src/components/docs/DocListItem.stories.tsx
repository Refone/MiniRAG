import type { Meta, StoryObj } from "@storybook/react-vite";
import { DocListItem } from "./DocListItem";
import { docsList } from "@/stories/fixtures";

const meta = {
  title: "Docs/DocListItem",
  component: DocListItem,
  args: {
    doc: docsList[0],
    selected: true,
    onSelect: () => {},
    onOpenPdf: () => {},
    onOpenChunks: () => {},
    onDelete: () => {},
  },
} satisfies Meta<typeof DocListItem>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 选中态 + PDF 文档（带 PDF 按钮） */
export const SelectedPdf: Story = {};

export const UnselectedMarkdown: Story = {
  args: { doc: docsList[1], selected: false },
};
