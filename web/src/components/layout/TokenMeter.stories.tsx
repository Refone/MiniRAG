import type { Meta, StoryObj } from "@storybook/react-vite";
import { TokenMeter } from "./TokenMeter";
import { useChatStore } from "@/store/chatStore";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import {
  emptyTokenUsage,
  largeTokenUsage,
  mockTokenUsage,
} from "@/stories/fixtures";
import type { TokenLoadStatus, TokenUsageSnapshot } from "@/types/tokenUsage";

/**
 * 故事加载器：在组件挂载前播种 store。
 * 必须用 loaders 而不是组件 effect —— TokenMeter 挂载时会拉取快照，
 * 子组件 effect 先于播种 effect 执行，mock 数据会被真实请求覆盖。
 */
function seedTokenMeter(
  snapshot: TokenUsageSnapshot | null,
  status: TokenLoadStatus,
  sending = false,
) {
  return async () => {
    useTokenUsageStore.setState({ snapshot, status, lastSource: null });
    useChatStore.setState({ sending });
    return {};
  };
}

const meta = {
  title: "Layout/TokenMeter",
  component: TokenMeter,
} satisfies Meta<typeof TokenMeter>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Data: Story = { loaders: [seedTokenMeter(mockTokenUsage, "ready")] };

export const Empty: Story = {
  loaders: [seedTokenMeter(emptyTokenUsage, "ready")],
};

export const Loading: Story = { loaders: [seedTokenMeter(null, "loading")] };

export const Error: Story = { loaders: [seedTokenMeter(null, "error")] };

export const Large: Story = {
  loaders: [seedTokenMeter(largeTokenUsage, "ready")],
};

export const Live: Story = {
  loaders: [seedTokenMeter(mockTokenUsage, "ready", true)],
};
