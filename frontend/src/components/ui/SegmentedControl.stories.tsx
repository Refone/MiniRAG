import { useState } from "react";
import type { Meta, StoryObj } from "@storybook/react-vite";
import { PREVIEW_MODES } from "@/lib/constants";
import { SegmentedControl } from "./SegmentedControl";

const meta = {
  title: "UI/SegmentedControl",
  component: SegmentedControl,
  args: {
    ariaLabel: "预览模式",
    options: PREVIEW_MODES,
    value: "markdown",
    onChange: () => {},
  },
} satisfies Meta<typeof SegmentedControl<string>>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 真实用法：文档预览的「原文 / 切块 / 特征」三选项 */
export const PreviewModes: Story = {};

/** 可交互：内部维护选中态，thumb 随选中项滑动 */
export const Interactive: Story = {
  render: function Render(args) {
    const [value, setValue] = useState(args.value);
    return <SegmentedControl {...args} value={value} onChange={setValue} />;
  },
};

/** 选项数不是 3 时 thumb 也应对齐（回归样张，防止再出现 /3 硬编码） */
export const TwoOptions: Story = {
  args: {
    ariaLabel: "筛选",
    options: [
      { value: "all", label: "全部" },
      { value: "done", label: "已完成" },
    ],
    value: "all",
  },
};

export const Disabled: Story = { args: { disabled: true } };
