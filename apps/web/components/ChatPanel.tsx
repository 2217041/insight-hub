"use client";

import { useEffect, useRef } from "react";

import type { Conversation } from "@/lib/types";
import { Composer } from "./Composer";
import { MessageItem } from "./MessageItem";

type Props = {
  conversation: Conversation | null;
  streaming: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onRetry: () => void;
  onNew: () => void;
};

export function ChatPanel({
  conversation,
  streaming,
  onSend,
  onStop,
  onRetry,
  onNew,
}: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const messageCount = conversation?.messages.length ?? 0;
  const lastContent = conversation?.messages.at(-1)?.content ?? "";

  // 新内容到达时滚到底部
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messageCount, lastContent]);

  if (!conversation) {
    return (
      <section className="flex flex-1 items-center justify-center bg-white">
        <div className="text-center">
          <h2 className="text-lg font-semibold text-gray-800">
            开始一段新对话
          </h2>
          <p className="mt-1 text-sm text-gray-500">
            先建一个会话，然后就能测试流式输出了
          </p>
          <button
            onClick={onNew}
            className="mt-4 rounded-xl bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500"
          >
            新建对话
          </button>
        </div>
      </section>
    );
  }

  return (
    <section className="flex min-w-0 flex-1 flex-col bg-white">
      <header className="flex items-center justify-between border-b border-gray-100 px-6 py-3">
        <h1 className="truncate text-sm font-medium text-gray-700">
          {conversation.title}
        </h1>
        <span className="text-xs text-gray-400">
          {conversation.messages.length} 条消息
        </span>
      </header>

      <div className="flex-1 overflow-y-auto px-6 py-6">
        <div className="mx-auto max-w-3xl space-y-5">
          {conversation.messages.length === 0 ? (
            <div className="py-20 text-center">
              <p className="text-sm text-gray-500">
                这个会话还是空的，问点什么吧
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-2">
                {["解释一下 SSE", "为什么不用 WebSocket", "流式输出怎么实现"].map(
                  (q) => (
                    <button
                      key={q}
                      onClick={() => onSend(q)}
                      className="rounded-full border border-gray-200 px-3 py-1 text-xs text-gray-600 transition hover:border-gray-400 hover:text-gray-900"
                    >
                      {q}
                    </button>
                  ),
                )}
              </div>
            </div>
          ) : (
            conversation.messages.map((m, i) => (
              <MessageItem
                key={m.id}
                message={m}
                onRetry={
                  m.role === "assistant" &&
                  m.status === "error" &&
                  i === conversation.messages.length - 1
                    ? onRetry
                    : undefined
                }
              />
            ))
          )}
          <div ref={bottomRef} />
        </div>
      </div>

      <Composer onSend={onSend} onStop={onStop} streaming={streaming} />
    </section>
  );
}