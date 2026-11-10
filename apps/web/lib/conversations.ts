"use client";

/** 会话相关的 API 封装。 */

import { getAccessToken } from "@/lib/auth";

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export type ConversationMeta = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
};

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: unknown[];
  created_at: string;
};

function authHeaders(): HeadersInit {
  const token = getAccessToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function toError(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as { message?: string; request_id?: string };
    return new Error(`${body.message ?? `HTTP ${res.status}`}${body.request_id ? `（${body.request_id}）` : ""}`);
  } catch {
    return new Error(`HTTP ${res.status}`);
  }
}

export async function listConversations(): Promise<ConversationMeta[]> {
  const res = await fetch(`${API_BASE}/api/conversations`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  const data = (await res.json()) as { items: ConversationMeta[] };
  return data.items;
}

export async function createConversation(title = "新对话"): Promise<ConversationMeta> {
  const res = await fetch(`${API_BASE}/api/conversations`, {
    method: "POST",
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ title }),
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as ConversationMeta;
}

export async function getConversation(
  id: string,
): Promise<{ conversation: ConversationMeta; messages: StoredMessage[] }> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, { headers: authHeaders() });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as { conversation: ConversationMeta; messages: StoredMessage[] };
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/api/conversations/${id}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  // 204 无响应体；404 说明已经没了，也当成功
  if (!res.ok && res.status !== 404) throw await toError(res);
}