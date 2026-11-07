export type Role = "user" | "assistant";

export type MessageStatus = "streaming" | "done" | "error";

export type Message = {
  id: string;
  role: Role;
  content: string;
  status: MessageStatus;
  error?: string;
  createdAt: number;
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
};

export type StreamEvent =
  | { type: "start"; message_id: string; conversation_id: string }
  | { type: "delta"; text: string }
  | {
      type: "done";
      message_id: string;
      conversation_id: string;
      usage?: { chars: number; elapsed_ms: number };
    }
  | { type: "error"; message: string };

export const newId = (): string =>
  typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `id-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function newConversation(): Conversation {
  const now = Date.now();
  return {
    id: newId(),
    title: "新对话",
    messages: [],
    createdAt: now,
    updatedAt: now,
  };
}

export function titleFrom(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 20 ? `${t.slice(0, 20)}…` : t || "新对话";
}