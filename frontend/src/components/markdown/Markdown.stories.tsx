import type { Meta, StoryObj } from "@storybook/react-vite";
import { MarkdownContent } from "./Markdown";

const richText = [
  "## 检索流程",
  "",
  "1. 查询向量化",
  "2. Milvus Top-K 召回",
  "3. 重排后交给大模型生成",
  "",
  "| 参数 | 默认值 | 说明 |",
  "| --- | --- | --- |",
  "| top_k | 5 | 召回条数 |",
  "| score_threshold | 0.6 | 相关度阈值 |",
  "",
  "> 提示：表格与代码块会整块保留。",
  "",
  "```python",
  "chunks = split_markdown(text, max_tokens=512)",
  "```",
  "",
  "参考 [Milvus 文档](https://milvus.io/docs)。",
].join("\n");

const htmlTable = [
  "### MinerU 解析出的表格",
  "",
  "<table><thead><tr><th>字段</th><th>类型</th></tr></thead>",
  "<tbody><tr><td>doc_id</td><td>string</td></tr>",
  "<tr><td>chunks</td><td>DocsChunkItem[]</td></tr></tbody></table>",
].join("\n");

const streamingText =
  "正在生成切块示意图：\n\n![切块流程](http://localhost:8000/api/image/chunk-flow";

const meta = {
  title: "Markdown/MarkdownContent",
  component: MarkdownContent,
  args: { text: richText },
} satisfies Meta<typeof MarkdownContent>;

export default meta;
type Story = StoryObj<typeof meta>;

/** GFM：表格 / 代码块 / 引用 / 链接 */
export const RichText: Story = {};

/** 文档页模式：允许原始 HTML（表格） */
export const HtmlTable: Story = {
  args: { text: htmlTable, allowHtml: true },
};

/** 流式输出：未闭合的图片语法先显示 shimmer 占位 */
export const StreamingImage: Story = {
  args: { text: streamingText, streaming: true },
};
