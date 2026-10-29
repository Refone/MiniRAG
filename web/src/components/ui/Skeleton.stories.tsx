import type { Meta, StoryObj } from "@storybook/react-vite";
import { Skeleton } from "./Skeleton";

const meta = {
  title: "UI/Skeleton",
  component: Skeleton,
  args: {},
} satisfies Meta<typeof Skeleton>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 默认 5 行（w60/w100/w100/w80/w40） */
export const Default: Story = {};

export const CustomWidths: Story = {
  args: { widths: ["w100", "w80", "w40"] },
};
