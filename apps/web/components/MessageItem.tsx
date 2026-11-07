"use client";

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Message } from "@/lib/types";

type Props = {
  message: Message;
  onRetry?: () => void;
};

export function MessageItem({ message, onRetry }: Props) {
  const isUser = message.role === "user";
  const streaming = message.status === "streaming";
  const failed = message.status === "error";

  return (
    <div className={`flex gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-emerald-100 text-xs font-semibold text-emerald-700">
          AI
        </div>
      )}

      <div className={`min-w-0 max-w-[78%] ${isUser ? "order-first" : ""}`}>
        <div
          className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
            isUser
              ? "bg-gray-900 text-white"
              : failed
                ? "bg-red-50 text-red-800 ring-1 ring-red-200"
                : "bg-white text-gray-800 ring-1 ring-gray-200"
          }`}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap break-words">{message.content}</p>
          ) : failed ? (
            <div>
              <p className="font-medium">回复失败</p>
              <p className="mt-1 text-xs opacity-80">{message.error}</p>
              {onRetry && (
                <button
                  onClick={onRetry}
                  className="mt-2 rounded-md border border-red-300 bg-white px-2.5 py-1 text-xs font-medium text-red-700 transition hover:bg-red-100"
                >
                  重试
                </button>
              )}
            </div>
          ) : (
            <div className="md">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content || ""}
              </ReactMarkdown>
              {streaming && (
                <span className="ml-0.5 inline-block h-4 w-[2px] animate-pulse bg-gray-500 align-middle" />
              )}
            </div>
          )}
        </div>

        {streaming && message.content === "" && (
          <p className="mt-1 pl-1 text-xs text-gray-400">正在生成…</p>
        )}
      </div>

      {isUser && (
        <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-gray-200 text-xs font-semibold text-gray-600">
          你
        </div>
      )}
    </div>
  );
}