"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ChatPanel } from "@/components/ChatPanel";
import { Sidebar } from "@/components/Sidebar";
import { streamChat } from "@/lib/api";
import { fetchMe, logout, type UserResponse } from "@/lib/auth";
import {
  createConversation as apiCreate,
  deleteConversation as apiDelete,
  getConversation,
  listConversations,
  type StoredMessage,
} from "@/lib/conversations";
import { newId, type Conversation, type Message } from "@/lib/types";

function toMessage(m: StoredMessage): Message {
  return {
    id: m.id,
    role: m.role,
    content: m.content,
    status: "done",
    createdAt: Date.parse(m.created_at) || Date.now(),
  };
}

export default function Page() {
  const router = useRouter();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [listLoading, setListLoading] = useState(true);
  const [streaming, setStreaming] = useState(false);
  const [user, setUser] = useState<UserResponse | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const userId = user?.id ?? null;

  // ---------- 登录态 ----------
  useEffect(() => {
    let alive = true;
    void fetchMe()
      .then((u) => alive && setUser(u))
      .catch(() => alive && setUser(null))
      .finally(() => alive && setAuthChecked(true));
    return () => {
      alive = false;
    };
  }, []);

  // ---------- 登录后拉会话列表（W5 收尾：数据在服务端，不再读 localStorage）----------
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!authChecked) return;
    if (!userId) {
      setConversations([]);
      setActiveId(null);
      setListLoading(false);
      return;
    }

    let alive = true;
    setListLoading(true);
    void listConversations()
      .then((items) => {
        if (!alive) return;
        const convs: Conversation[] = items.map((it) => ({
          id: it.id,
          title: it.title,
          messages: [],
          createdAt: Date.parse(it.created_at) || Date.now(),
          updatedAt: Date.parse(it.updated_at) || Date.now(),
        }));
        setConversations(convs);
        setActiveId((prev) => (prev && convs.some((c) => c.id === prev) ? prev : (convs[0]?.id ?? null)));
      })
      .catch(() => alive && setConversations([]))
      .finally(() => alive && setListLoading(false));

    return () => {
      alive = false;
    };
  }, [authChecked, userId]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // ---------- 选中会话时按需拉消息 ----------
  useEffect(() => {
    if (!activeId) return;
    const target = conversations.find((c) => c.id === activeId);
    if (!target || target.messages.length > 0) return;

    let alive = true;
    void getConversation(activeId)
      .then(({ messages }) => {
        if (!alive) return;
        setConversations((prev) =>
          prev.map((c) => (c.id === activeId ? { ...c, messages: messages.map(toMessage) } : c)),
        );
      })
      .catch(() => undefined);

    return () => {
      alive = false;
    };
  }, [activeId, conversations]);

  const handleLogout = useCallback(() => {
    logout();
    setUser(null);
    setConversations([]);
    setActiveId(null);
    router.push("/login");
  }, [router]);

  const patchMessage = useCallback((convId: string, msgId: string, patch: Partial<Message>) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id !== convId
          ? c
          : { ...c, messages: c.messages.map((m) => (m.id === msgId ? { ...m, ...patch } : m)) },
      ),
    );
  }, []);

  const appendToMessage = useCallback((convId: string, msgId: string, delta: string) => {
    setConversations((prev) =>
      prev.map((c) =>
        c.id !== convId
          ? c
          : {
              ...c,
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
      if (!trimmed || streaming || !userId) return;

      setStreaming(true);
      let convId = activeId;

      // 没有会话先在后端建一个（标题由后端按首条消息生成）
      if (!convId) {
        try {
          const created = await apiCreate(trimmed.slice(0, 20) || "新对话");
          convId = created.id;
          setConversations((prev) => [
            { id: created.id, title: created.title, messages: [], createdAt: Date.now(), updatedAt: Date.now() },
            ...prev,
          ]);
          setActiveId(created.id);
        } catch {
          setStreaming(false);
          return;
        }
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
          c.id !== convId ? c : { ...c, messages: [...c.messages, userMsg, aiMsg] },
        ),
      );

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const ev of streamChat({ message: trimmed, conversation_id: convId }, controller.signal)) {
          if (ev.type === "delta") {
            appendToMessage(convId, aiMsg.id, ev.text);
          } else if (ev.type === "done") {
            patchMessage(convId, aiMsg.id, { status: "done" });
          } else if (ev.type === "error") {
            throw new Error(ev.message);
          }
        }
        patchMessage(convId, aiMsg.id, { status: "done" });
      } catch (err) {
        if (controller.signal.aborted) {
          patchMessage(convId, aiMsg.id, { status: "done" });
        } else {
          patchMessage(convId, aiMsg.id, {
            status: "error",
            error: err instanceof Error ? err.message : "未知错误",
          });
        }
      } finally {
        abortRef.current = null;
        setStreaming(false);
      }
    },
    [activeId, appendToMessage, patchMessage, streaming, userId],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const retry = useCallback(() => {
    const conv = conversations.find((c) => c.id === activeId);
    if (!conv) return;
    const lastUser = [...conv.messages].reverse().find((m) => m.role === "user");
    if (!lastUser) return;

    const cleaned = [...conv.messages];
    while (cleaned.length > 0 && cleaned[cleaned.length - 1].status === "error") cleaned.pop();
    setConversations((prev) => prev.map((c) => (c.id === conv.id ? { ...c, messages: cleaned } : c)));
    void send(lastUser.content);
  }, [activeId, conversations, send]);

  const createConversation = useCallback(async () => {
    if (streaming || !userId) return;
    try {
      const created = await apiCreate();
      setConversations((prev) => [
        { id: created.id, title: created.title, messages: [], createdAt: Date.now(), updatedAt: Date.now() },
        ...prev,
      ]);
      setActiveId(created.id);
    } catch {
      // 建会话失败不阻断，用户再点一次即可
    }
  }, [streaming, userId]);

  const deleteConversation = useCallback(
    async (id: string) => {
      if (streaming && id === activeId) stop();
      try {
        await apiDelete(id);
      } catch {
        return;
      }
      setConversations((prev) => {
        const next = prev.filter((c) => c.id !== id);
        if (id === activeId) setActiveId(next[0]?.id ?? null);
        return next;
      });
    },
    [activeId, stop, streaming],
  );

  if (!authChecked) {
    return (
      <div className="flex h-screen">
        <div className="w-64 shrink-0 border-r border-gray-200 bg-gray-50/60" />
        <div className="flex flex-1 items-center justify-center">
          <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-300 border-t-gray-800" />
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <main className="flex min-h-screen items-center justify-center bg-gray-50 px-6">
        <div className="text-center">
          <h1 className="text-xl font-semibold text-gray-900">Insight Hub</h1>
          <p className="mt-2 text-sm text-gray-500">登录后才能开始对话</p>
          <a
            href="/login"
            className="mt-5 inline-block rounded-xl bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white transition hover:bg-emerald-500"
          >
            去登录 / 注册
          </a>
          <p className="mt-4 text-xs text-gray-400">会话保存在服务端，换设备也能继续</p>
        </div>
      </main>
    );
  }

  const active = conversations.find((c) => c.id === activeId) ?? null;

  return (
    <div className="flex h-screen overflow-hidden bg-gray-100/40">
      <Sidebar
        conversations={conversations}
        activeId={activeId}
        onSelect={(id) => !streaming && setActiveId(id)}
        onNew={() => void createConversation()}
        onDelete={(id) => void deleteConversation(id)}
        user={user}
        onLogout={handleLogout}
      />
      <ChatPanel
        conversation={active}
        streaming={streaming || listLoading}
        onSend={(t) => void send(t)}
        onStop={stop}
        onRetry={retry}
        onNew={() => void createConversation()}
      />
    </div>
  );
}