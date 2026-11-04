/** id 生成纯函数（chatStore 与 docsStore 共用） */

export function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2)}${Date.now().toString(36)}`;
}
