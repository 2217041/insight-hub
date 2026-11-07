"use client";

import { useEffect, useRef, useState } from "react";

type Props = {
  onSend: (text: string) => void;
  onStop: () => void;
  streaming: boolean;
  disabled?: boolean;
};

export function Composer({ onSend, onStop, streaming, disabled }: Props) {
  const [text, setText] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  // 高度自适应：最多 6 行
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 168)}px`;
  }, [text]);

  const canSend = !streaming && !disabled && text.trim().length > 0;

  function submit() {
    if (!canSend) return;
    onSend(text.trim());
    setText("");
  }

  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3">
      <div className="mx-auto max-w-3xl">
        <div className="flex items-end gap-2 rounded-2xl border border-gray-200 bg-white p-2 shadow-sm focus-within:border-gray-400">
          <textarea
            ref={ref}
            rows={1}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              // Enter 发送，Shift+Enter 换行；输入法组合中不触发
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                submit();
              }
            }}
            placeholder="问点什么…（Enter 发送，Shift + Enter 换行）"
            className="max-h-[168px] flex-1 resize-none bg-transparent px-2 py-2 text-sm outline-none placeholder:text-gray-400"
            disabled={disabled}
          />

          {streaming ? (
            <button
              onClick={onStop}
              className="rounded-xl bg-gray-900 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-gray-700"
              title="停止生成"
            >
              停止
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              className="rounded-xl bg-emerald-600 px-3.5 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:bg-gray-300"
            >
              发送
            </button>
          )}
        </div>

        <p className="mt-2 text-center text-[11px] text-gray-400">
          W2 阶段回复是后端占位内容，用于验证流式链路；W9 接入真实模型
        </p>
      </div>
    </div>
  );
}