import type { Meta, StoryObj } from "@storybook/react-vite";
import { UploadDropzone } from "./UploadDropzone";

const meta = {
  title: "Docs/UploadDropzone",
  component: UploadDropzone,
  args: { onFiles: () => {} },
  render: (args) => (
    <div style={{ width: 460 }}>
      <UploadDropzone {...args} />
    </div>
  ),
} satisfies Meta<typeof UploadDropzone>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 拖拽 / 点击选择文件（点击会打开系统文件选择框） */
export const Default: Story = {};
