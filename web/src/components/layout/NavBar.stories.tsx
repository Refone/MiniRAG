import type { Meta, StoryObj } from "@storybook/react-vite";
import { NavBar } from "./NavBar";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import { mockTokenUsage } from "@/stories/fixtures";

const meta = {
  title: "Layout/NavBar",
  component: NavBar,
  // 挂载前播种 Token 快照：NavBar 内的 TokenMeter 有数据可展示、不触发真实请求
  loaders: [
    async () => {
      useTokenUsageStore.setState({
        snapshot: mockTokenUsage,
        status: "ready",
        lastSource: null,
      });
      return {};
    },
  ],
  args: {
    page: "chat",
    theme: "light",
    onPageChange: () => {},
    onToggleTheme: () => {},
  },
} satisfies Meta<typeof NavBar>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Chat: Story = {};

export const Docs: Story = { args: { page: "docs" } };
