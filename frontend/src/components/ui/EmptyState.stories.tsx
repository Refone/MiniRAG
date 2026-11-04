import type { Meta, StoryObj } from "@storybook/react-vite";
import { EmptyState } from "./EmptyState";
import { InboxIcon } from "@/components/icons/AppIcons";

const meta = {
  title: "UI/EmptyState",
  component: EmptyState,
  args: {
    icon: <InboxIcon />,
    title: "文库为空",
    subtitle: "点击左上角「添加文档」导入第一篇文档",
    className: "doc-list-empty",
  },
  argTypes: { icon: { control: false } },
} satisfies Meta<typeof EmptyState>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const TitleOnly: Story = {
  args: { icon: undefined, subtitle: undefined },
};
