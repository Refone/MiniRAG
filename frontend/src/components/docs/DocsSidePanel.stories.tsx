import type { Meta, StoryObj } from "@storybook/react-vite";
import { userEvent, within } from "storybook/test";
import { DocsSidePanel } from "./DocsSidePanel";
import { docsList, importFile, importZipFile } from "@/stories/fixtures";

const meta = {
  title: "Docs/DocsSidePanel",
  component: DocsSidePanel,
  args: {
    docs: docsList,
    total: docsList.length,
    refreshing: false,
    selectedId: "doc_1001",
    files: [importFile],
    onRefresh: () => {},
    onSelect: () => {},
    onDeleteRequest: () => {},
    onUploadFiles: () => {},
  },
  render: (args) => (
    <div style={{ height: 620, display: "flex" }}>
      <DocsSidePanel {...args} />
    </div>
  ),
} satisfies Meta<typeof DocsSidePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 文档列表视图（默认） */
export const DocumentList: Story = {};

/** 点「添加文档」切到导入视图：单文件 + ZIP 子任务树 */
export const ImportTasks: Story = {
  args: { files: [importFile, importZipFile] },
  play: async ({ canvasElement }) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole("button", { name: "添加文档" }));
  },
};

export const Empty: Story = {
  args: { docs: [], total: 0, selectedId: null, files: [] },
};
