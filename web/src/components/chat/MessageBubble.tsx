import { memo } from "react";
import type { ReactNode } from "react";
import { MarkdownContent } from "@/components/markdown/Markdown";
import { SparkIcon } from "@/components/icons/AppIcons";
import type { ChatMessage } from "@/types/chat";

interface AnswerContentProps {
  text: string;
  streaming?: boolean;
  showPlaceholder?: boolean;
}

function AnswerContent({
  text,
  streaming = false,
  showPlaceholder,
}: AnswerContentProps) {
  const display =
    text.trim().length > 0
      ? text
      : showPlaceholder
        ? "（已完成，但未返回答案）"
        : "";

  return (
    <>{display && <MarkdownContent text={display} streaming={streaming} />}</>
  );
}

/** 单条消息（user/bot、typing/error/answer 全形态）；memo 剪枝 (BUG-004) */
export const MessageBubble = memo(function MessageBubble({
  message,
}: {
  message: ChatMessage;
}) {
  if (message.role === "user") {
    return (
      <div className="msg user">
        <div className="user-row">
          <div className="bubble">{message.text}</div>
          <div className="meta">{message.time}</div>
        </div>
      </div>
    );
  }

  let content: ReactNode;
  if (message.error) {
    content = (
      <div className="answer">
        抱歉，本次处理失败：{"\n"}
        {message.error}
      </div>
    );
  } else if (message.typing) {
    content = (
      <span className="typing">
        <span className="dot" />
        <span className="dot" />
        <span className="dot" />
      </span>
    );
  } else {
    content = (
      <AnswerContent
        text={message.text}
        streaming={message.streaming}
        showPlaceholder
      />
    );
  }

  return (
    <div className="msg bot">
      <div className="avatar bot" aria-hidden="true">
        <SparkIcon />
      </div>
      <div className="bot-body">
        {content}
        <div className="meta">{message.hint ?? message.time}</div>
      </div>
    </div>
  );
});
