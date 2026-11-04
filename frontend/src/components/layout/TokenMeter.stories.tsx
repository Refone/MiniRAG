import type { Meta, StoryObj } from "@storybook/react-vite";
import { useEffect } from "react";
import { TokenMeter } from "./TokenMeter";
import { useChatStore } from "@/store/chatStore";
import { useTokenUsageStore } from "@/store/tokenUsageStore";
import {
  emptyTokenUsage,
  largeTokenUsage,
  mockTokenUsage,
  tokenUsageAfterDelta,
} from "@/stories/fixtures";
import type { TokenLoadStatus, TokenUsageSnapshot } from "@/types/tokenUsage";

/** 故事内模拟的 SSE 通道（与 mock 快照的 session_id 一致） */
const CHANNEL = "sess-demo-token";

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
    useTokenUsageStore.setState({
      snapshot,
      status,
      lastSource: null,
      lastDelta: null,
      pending: {},
    });
    useChatStore.setState({ sending });
    return {};
  };
}

/** 按真实时序注入三次模型调用增量（usage-delta）+ 请求结束快照帧：chip 数字实时增长后回落到权威值 */
function RealtimePlayer() {
  useEffect(() => {
    const timers = [
      window.setTimeout(
        () =>
          useTokenUsageStore
            .getState()
            .applyDelta("llm", 300, "query", CHANNEL),
        900,
      ),
      window.setTimeout(
        () =>
          useTokenUsageStore
            .getState()
            .applyDelta("embedding", 200, "query", CHANNEL),
        1900,
      ),
      window.setTimeout(
        () =>
          useTokenUsageStore
            .getState()
            .applyDelta("reranker", 300, "query", CHANNEL),
        2900,
      ),
      window.setTimeout(
        () =>
          useTokenUsageStore
            .getState()
            .applySnapshot(tokenUsageAfterDelta, "query", CHANNEL),
        3900,
      ),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);
  return <TokenMeter />;
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

export const Realtime: Story = {
  loaders: [seedTokenMeter(mockTokenUsage, "ready", true)],
  render: () => <RealtimePlayer />,
};
