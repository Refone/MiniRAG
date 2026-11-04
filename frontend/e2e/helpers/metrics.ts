import { expect, type Page } from "@playwright/test";

/** 一次布局快照：会话滚动状态 + 输入卡位置 + 卡片占位高度 */
export interface ChatLayout {
  scrollTop: number;
  scrollHeight: number;
  clientHeight: number;
  paddingBottom: number;
  taskSlotHeight: number;
  composerVar: string;
  composerRect: { x: number; y: number; width: number; height: number };
}

export async function readChatLayout(page: Page): Promise<ChatLayout> {
  return page.evaluate(() => {
    const chat = document.querySelector<HTMLElement>(".chat");
    const pageEl = document.querySelector<HTMLElement>(".chat-page");
    const slot = document.querySelector<HTMLElement>(".task-slot");
    const composer = document.querySelector<HTMLElement>(".composer");
    if (!chat || !pageEl || !slot || !composer) {
      throw new Error(
        "布局节点缺失：需要 .chat / .chat-page / .task-slot / .composer",
      );
    }
    const rect = composer.getBoundingClientRect();
    return {
      scrollTop: chat.scrollTop,
      scrollHeight: chat.scrollHeight,
      clientHeight: chat.clientHeight,
      paddingBottom: parseFloat(getComputedStyle(chat).paddingBottom),
      taskSlotHeight: slot.getBoundingClientRect().height,
      composerVar: pageEl.style.getPropertyValue("--composer-h"),
      composerRect: {
        x: rect.x,
        y: rect.y,
        width: rect.width,
        height: rect.height,
      },
    };
  });
}

/**
 * 任务卡片开合前后：会话滚动位置 / 滚动高度 / 底部留白 / 卡片占位 / 输入卡位置
 * 全部不变（这是"历史会话与任务卡片解耦"的断言本体）。
 */
export function expectLayoutStable(before: ChatLayout, after: ChatLayout): void {
  expect(Math.abs(after.scrollTop - before.scrollTop)).toBeLessThanOrEqual(1);
  expect(Math.abs(after.scrollHeight - before.scrollHeight)).toBeLessThanOrEqual(
    1,
  );
  expect(after.clientHeight).toBe(before.clientHeight);
  expect(
    Math.abs(after.paddingBottom - before.paddingBottom),
  ).toBeLessThanOrEqual(1);
  expect(after.taskSlotHeight).toBe(before.taskSlotHeight);
  expect(after.composerVar).toBe(before.composerVar);
  for (const key of ["x", "y", "width", "height"] as const) {
    expect(
      Math.abs(after.composerRect[key] - before.composerRect[key]),
    ).toBeLessThanOrEqual(1);
  }
}

/** 等会话停在最新消息（距底部 ≤ 2px） */
export async function waitForChatPinned(page: Page): Promise<void> {
  await expect
    .poll(
      () =>
        page.evaluate(() => {
          const chat = document.querySelector<HTMLElement>(".chat");
          if (!chat) return Number.POSITIVE_INFINITY;
          return chat.scrollHeight - chat.scrollTop - chat.clientHeight;
        }),
      { message: "会话应停在最新消息（贴底）" },
    )
    .toBeLessThanOrEqual(2);
}

/** 当前会话 scrollTop（-1 表示节点缺失） */
export async function readScrollTop(page: Page): Promise<number> {
  return page.evaluate(
    () => document.querySelector<HTMLElement>(".chat")?.scrollTop ?? -1,
  );
}
