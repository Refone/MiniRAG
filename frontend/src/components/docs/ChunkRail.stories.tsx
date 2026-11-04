import { useRef } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { ChunkCard } from "@/components/docs/ChunkCard";
import { ChunkRail } from "./ChunkRail";
import { chunks } from "@/stories/fixtures";

const meta = {
  title: "Docs/ChunkRail",
  component: ChunkRail,
  args: { containerRef: { current: null }, chunks, resetKey: "story:chunks" },
} satisfies Meta<typeof ChunkRail>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 放在与预览区一致的滚动容器里：悬停看长度、点击定位、滚动高亮 */
export const InPreview: Story = {
  render: function Render(args) {
    const scrollRef = useRef<HTMLDivElement | null>(null);
    return (
      <div style={{ height: 560, display: "flex" }}>
        <div className="preview-panel elevated">
          <div className="preview-body">
            <div className="preview-scroll" ref={scrollRef}>
              <div className="preview-inner">
                {chunks.map((chunk, index) => (
                  <ChunkCard
                    key={index}
                    index={index}
                    chunk={chunk}
                    showSplit={index < chunks.length - 1}
                  />
                ))}
              </div>
            </div>
            <ChunkRail {...args} containerRef={scrollRef} resetKey="story:chunks" />
          </div>
        </div>
      </div>
    );
  },
};
