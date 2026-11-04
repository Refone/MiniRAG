import type { Meta, StoryObj } from "@storybook/react-vite";
import { useState } from "react";
import { TokenPanel } from "./TokenPanel";
import {
  emptyTokenUsage,
  largeTokenUsage,
  mockTokenUsage,
} from "@/stories/fixtures";
import type {
  TokenLoadStatus,
  TokenScope,
  TokenUsageSnapshot,
} from "@/types/tokenUsage";

interface PanelStoryProps {
  snapshot?: TokenUsageSnapshot | null;
  status?: TokenLoadStatus;
  live?: boolean;
  initialScope?: TokenScope;
}

/** 面板宿主：静态定位模拟 TokenMeter 的 .token-panel 容器 */
function PanelHost({
  snapshot = mockTokenUsage,
  status = "ready",
  live = false,
  initialScope = "total",
}: PanelStoryProps) {
  const [scope, setScope] = useState<TokenScope>(initialScope);
  return (
    <div
      className="token-panel"
      style={{ position: "static", width: 360 }}
    >
      <TokenPanel
        sessionId={snapshot?.session_id ?? "sess-demo-token"}
        status={status}
        scope={scope}
        snapshot={snapshot ?? null}
        live={live}
        flashKinds={[]}
        onScopeChange={setScope}
        onRetry={() => {}}
        onClose={() => {}}
        onFlashEnd={() => {}}
        onResetRequest={() => {}}
        resetDisabled={live}
      />
    </div>
  );
}

const meta = {
  title: "Layout/TokenPanel",
  component: TokenPanel,
  args: {
    sessionId: "sess-demo-token",
    status: "ready",
    scope: "total",
    snapshot: mockTokenUsage,
    live: false,
    flashKinds: [],
    onScopeChange: () => {},
    onRetry: () => {},
    onClose: () => {},
    onFlashEnd: () => {},
    onResetRequest: () => {},
    resetDisabled: false,
  },
} satisfies Meta<typeof TokenPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Total: Story = {
  render: () => <PanelHost />,
};

export const Query: Story = {
  render: () => <PanelHost initialScope="query" />,
};

export const Upload: Story = {
  render: () => <PanelHost initialScope="upload" />,
};

export const Empty: Story = {
  render: () => <PanelHost snapshot={emptyTokenUsage} />,
};

export const Loading: Story = {
  render: () => <PanelHost snapshot={null} status="loading" />,
};

export const Error: Story = {
  render: () => <PanelHost snapshot={null} status="error" />,
};

export const Large: Story = {
  render: () => <PanelHost snapshot={largeTokenUsage} />,
};

export const Live: Story = {
  render: () => <PanelHost live />,
};
