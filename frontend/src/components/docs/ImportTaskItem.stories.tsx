import type { Meta, StoryObj } from "@storybook/react-vite";
import { ImportTaskItem } from "./ImportTaskItem";
import {
  importFile,
  importFileComplete,
  importFileFailed,
  importZipFile,
} from "@/stories/fixtures";

const meta = {
  title: "Docs/ImportTaskItem",
  component: ImportTaskItem,
  args: { file: importFile },
  render: (args) => (
    <div style={{ width: 420 }}>
      <ImportTaskItem {...args} />
    </div>
  ),
} satisfies Meta<typeof ImportTaskItem>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Processing: Story = {};

/** ZIP fork：父卡 + 子任务树（完成 / 进行中 / 等待 / 失败 / 未完成） */
export const ZipFork: Story = {
  args: { file: importZipFile },
};

export const Complete: Story = {
  args: { file: importFileComplete },
};

export const Failed: Story = {
  args: { file: importFileFailed },
};
