import type { Meta, StoryObj } from "@storybook/react-vite";
import { FeaturePanel } from "./FeaturePanel";
import { docsDetail } from "@/stories/fixtures";

const meta = {
  title: "Docs/FeaturePanel",
  component: FeaturePanel,
  args: { keywords: docsDetail.keywords, abstract: docsDetail.abstract },
} satisfies Meta<typeof FeaturePanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {};

export const Empty: Story = {
  args: { keywords: "", abstract: "" },
};
