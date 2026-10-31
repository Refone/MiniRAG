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

/** 挂载后按真实时序注入：三次模型调用增量（usage-delta）+ 请求结束快照帧，验证气泡队列 */
function DeltaPlayer() {
  useEffect(() => {
    const timers = [
      window.setTimeout(
        () => useTokenUsageStore.getState().applyDelta("llm", 300, "query"),
        900,
      ),
      window.setTimeout(
        () => useTokenUsageStore.getState().applyDelta("embedding", 200, "query"),
        1900,
      ),
      window.setTimeout(
        () => useTokenUsageStore.getState().applyDelta("reranker", 300, "query"),
        2900,
      ),
      window.setTimeout(
        () =>
          useTokenUsageStore.setState({
            snapshot: tokenUsageAfterDelta,
            status: "ready",
            lastSource: "query",
          }),
        3900,
      ),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, []);
  return <TokenMeter />;
}

/** 挂载 6s 后只应用请求结束快照（无 usage-delta）：仅弹「+N tokens」总气泡 */
function TotalPlayer() {
  useEffect(() => {
    const timer = window.setTimeout(() => {
      useTokenUsageStore.setState({
        snapshot: tokenUsageAfterDelta,
        status: "ready",
        lastSource: "query",
      });
    }, 6000);
    return () => window.clearTimeout(timer);
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

export const DeltaBubbles: Story = {
  loaders: [seedTokenMeter(mockTokenUsage, "ready")],
  render: () => <DeltaPlayer />,
};

export const TotalBubble: Story = {
  loaders: [seedTokenMeter(mockTokenUsage, "ready")],
  render: () => <TotalPlayer />,
};
