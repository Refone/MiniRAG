import { createRef, useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChatComposer } from "./ChatComposer";

/** 页面容器 ref：ChatComposer 用它计算 textarea 的动态高度上限 */
const containerRef = createRef<HTMLDivElement>();

const meta = {
  title: "Chat/ChatComposer",
  component: ChatComposer,
  parameters: { layout: "fullscreen" },
  args: {
    value: "",
    onChange: () => {},
    onSend: () => {},
    sending: false,
    enableWebSearch: true,
    enableHyde: true,
    onToggleWebSearch: () => {},
    onToggleHyde: () => {},
    apiConnected: true,
    onClearHistory: () => {},
    showScrollToBottom: false,
    onScrollToBottom: () => {},
    containerRef,
  },
} satisfies Meta<typeof ChatComposer>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 可交互：输入、发送、工具开关、回到底部 */
export const Interactive: Story = {
  render: function Render(args) {
    const [value, setValue] = useState("MiniRAG 的切块策略是什么？");
    const [webSearch, setWebSearch] = useState(args.enableWebSearch);
    const [hyde, setHyde] = useState(args.enableHyde);
    const [sending, setSending] = useState(false);
    return (
      <div
        ref={containerRef}
        style={{
          height: 560,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
        }}
      >
        <ChatComposer
          {...args}
          value={value}
          onChange={setValue}
          sending={sending}
          enableWebSearch={webSearch}
          enableHyde={hyde}
          onToggleWebSearch={() => setWebSearch((v) => !v)}
          onToggleHyde={() => setHyde((v) => !v)}
          onSend={() => {
            setSending(true);
            setValue("");
            window.setTimeout(() => setSending(false), 1200);
          }}
        />
      </div>
    );
  },
};

/** 服务未连接 + 空输入 */
export const Offline: Story = {
  args: { apiConnected: false, value: "" },
  render: function Render(args) {
    return (
      <div
        ref={containerRef}
        style={{
          height: 560,
          display: "flex",
          flexDirection: "column",
          justifyContent: "flex-end",
        }}
      >
        <ChatComposer {...args} />
      </div>
    );
  },
};
