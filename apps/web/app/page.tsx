"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { Sidebar } from "@/components/Sidebar";
import { streamChat } from "@/lib/api";
import {
  loadActiveId,
  loadConversations,
  saveActiveId,
  saveConversations,
} from "@/lib/storage";
import {
  newConversation,
  newId,
  titleFrom,
  type Conversation,
  type Message,
} from "@/lib/types";

export default function Page() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // ---------- 首次挂载：从 localStorage 恢复 ----------
  // 这里必须在 effect 里读，不能放进 useState 初始值：
  // 服务端渲染时没有 localStorage，初始值不同会导致 hydration 不一致。
  // 因此显式豁免 react-hooks/set-state-in-effect（这是一次性的外部状态同步）。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    const list = loadConversations();
    setConversations(list);
    const savedActive = loadActiveId();
    setActiveId(
      savedActive && list.some((c) => c.id === savedActive)
        ? savedActive
        : (list[0]?.id ?? null),
    );
    setHydrated(true);
  }, []);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ---------- 变化即保存 ----------
  useEffect(() => {
    if (!hydrated) return;
    saveConversations(conversations);
    saveActiveId(activeId);
  }, [conversations, activeId, hydrated]);

  const active = conversations.find((c) => c.id === activeId) ?? null;

  // 局部更新某条消息
  const patchMessage = useCallback(
    (convId: string, msgId: string, patch: Partial<Message>) => {
      setConversations((prev) =>
        prev.map((c) =>
          c.id !== convId
            ? c
            : {
                ...c,
                updatedAt: Date.now(),
                messages: c.messages.map((m) =>
                  m.id === msgId ? { ...m, ...patch } : m,
                ),
              },
        ),
      );
    },
    [],
  );

  const appendToMessage = useCallback((convId: string, msgId: string, delta: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id !== convId
          ? c
          : {
              ...c,
              updatedAt: Date.now(),
              messages: c.messages.map((m) =>
                m.id === msgId ? { ...m, content: m.content + delta } : m,
              ),
            },
      ),
    );
  }, []);

  // ---------- 发送 ----------
  const send = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || streaming) return;

      // 没有会话就现场建一个
      let convId = activeId;
      if (!convId || !conversations.some((c) => c.id === convId)) {
        const created = newConversation();
        convId = created.id;
        setConversations((prev) => [created, ...prev]);
        setActiveId(convId);
      }

      const userMsg: Message = {
        id: newId(),
        role: "user",
        content: trimmed,
        status: "done",
        createdAt: Date.now(),
      };
      const aiMsg: Message = {
        id: newId(),
        role: "assistant",
        content: "",
        status: "streaming",
        createdAt: Date.now(),
      };

      setConversations((prev) =>
        prev.map((c) =>
          c.id !== convId
            ? c
            : {
                ...c,
                title: c.title === "新对话" ? titleFrom(trimmed) : c.title,
                messages: [...c.messages, userMsg, aiMsg],
                updatedAt: Date.now(),
              },
        ),
      );

      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      try {
        for await (const ev of streamChat(
          { message: trimmed, conversation_id: convId },
          controller.signal,
        )) {
          if (ev.type === "delta") {
            appendToMessage(convId, aiMsg.id, ev.text);
          } else if (ev.type === "done") {
            patchMessage(convId, aiMsg.id, { status: "done" });
          } else if (ev.type === "error") {
            throw new Error(ev.message);
          }
        }
        // 流结束但没收到 done（例如服务端提前关闭）
        patchMessage(convId, aiMsg.id, { status: "done" });
      } catch (err) {
        if (controller.signal.aborted) {
          // 用户点了停止：保留已生成内容
          patchMessage(convId, aiMsg.id, { status: "done" });
        } else {
          const msg =
            err instanceof Error ? err.message : "未知错误，请稍后重试";
          patchMessage(convId, aiMsg.id, { status: "error", error: msg });
        }
      } finally {
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [activeId, appendToMessage, conversations, patchMessage, streaming],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const retry = useCallback(() => {
    const conv = conversations.find((c) => c.id === activeId);
    if (!conv) return;

    const lastUser = [...conv.messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;

    // 去掉结尾失败的助手消息，再重发
    const cleaned = [...conv.messages];
    while (
      cleaned.length > 0 &&
      cleaned[cleaned.length - 1].role === "assistant" &&
      cleaned[cleaned.length - 1].status === "error"
    ) {
      cleaned.pop();
    }
    setConversations((prev) =>
      prev.map((c) => (c.id === conv.id ? { ...c, messages: cleaned } : c)),
    );

    void send(lastUser.content);
  }, [activeId, conversations, send]);

  const createConversation = useCallback(() => {
    if (streaming) return;
    const created = newConversation();
    setConversations((prev) => [created, ...prev]);
    setActiveId(created.id);
  }, [streaming]);

  const deleteConversation = useCallback(
    (id: string) => {
      if (streaming && id === activeId) stop();
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (id === activeId) setActiveId(next[0]?.id ?? null);
        return next;
      });
    },
    [activeId, stop, streaming],
  );

  // ---------- 首屏：等 localStorage 读完再渲染，避免闪烁 ----------
  if (!hydrated) {
    return (
      <div className="flex h-screen">
        <div className="w-64 shrink-0 border-r border-gray-200 bg-gray-50/60" />
        <div className="flex flex-1 items-center justify-center">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-800" />
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gray-100/40">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => !streaming && setActiveId(id)}
        onNew={createConversation}
        onDelete={deleteConversation}
      />
      <ChatPanel
        conversation={active}
        streaming={streaming}
        onSend={(t) => void send(t)}
        onStop={stop}
        onRetry={retry}
        onNew={createConversation}
      />
    </div>
  );
}