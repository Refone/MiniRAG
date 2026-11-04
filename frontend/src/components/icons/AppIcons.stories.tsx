import type { Meta, StoryObj } from "@storybook/react-vite";
import {
  ArrowDownIcon,
  BookIcon,
  ChatIcon,
  CloseIcon,
  FileIcon,
  ForkIcon,
  InboxIcon,
  MoonIcon,
  ScissorsIcon,
  SparkIcon,
  SunIcon,
  UploadIcon,
} from "./AppIcons";

/** 全部线性图标：颜色继承 currentColor（app 内由 .icon / 容器控制尺寸） */
const icons = [
  { name: "ChatIcon", Icon: ChatIcon },
  { name: "BookIcon", Icon: BookIcon },
  { name: "SunIcon", Icon: SunIcon },
  { name: "MoonIcon", Icon: MoonIcon },
  { name: "SparkIcon", Icon: SparkIcon },
  { name: "InboxIcon", Icon: InboxIcon },
  { name: "FileIcon", Icon: FileIcon },
  { name: "ForkIcon", Icon: ForkIcon },
  { name: "UploadIcon", Icon: UploadIcon },
  { name: "ArrowDownIcon", Icon: ArrowDownIcon },
  { name: "CloseIcon", Icon: CloseIcon },
  { name: "ScissorsIcon", Icon: ScissorsIcon },
];

const meta = {
  title: "Icons/AppIcons",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const Gallery: Story = {
  render: () => (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(120px, 1fr))",
        gap: 12,
      }}
    >
      {icons.map(({ name, Icon }) => (
        <div
          key={name}
          style={{
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 10,
            padding: 14,
            border: "1px solid var(--border)",
            borderRadius: 12,
            background: "var(--surface)",
            color: "var(--text-2)",
          }}
        >
          <Icon />
          <code style={{ fontSize: 11 }}>{name}</code>
        </div>
      ))}
    </div>
  ),
};
