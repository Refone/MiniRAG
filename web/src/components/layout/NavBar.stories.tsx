import type { Meta, StoryObj } from "@storybook/react-vite";
import { NavBar } from "./NavBar";

const meta = {
  title: "Layout/NavBar",
  component: NavBar,
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
