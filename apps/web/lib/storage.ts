import type { Conversation } from "./types";

const KEY = "insight-hub:conversations:v1";
const ACTIVE_KEY = "insight-hub:active:v1";

/**
 * W2 阶段的持久化方案：localStorage。
 *
 * 为什么先不用数据库：
 * - 本周的目标是"把交互跑通"，存哪儿不影响；
 * - 存数据库需要建表 + 鉴权 + 用户隔离，那是 W3/W4 的事。
 * 代价说清楚：换浏览器就没了、多标签页可能覆盖、没有跨设备。
 */
export function loadConversations(): Conversation[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    if (!Array.isArray(parsed)) return [];
    // 刷新时仍标记为 streaming 的消息，说明是被中断的
    return parsed.map((c) => ({
      ...c,
      messages: c.messages.map((m) =>
        m.status === "streaming"
          ? { ...m, status: "error" as const, error: "页面刷新，生成被中断" }
          : m,
      ),
    }));
  } catch {
    return [];
  }
}

export function saveConversations(list: Conversation[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // 配额满或隐私模式：静默失败，不影响使用
  }
}

export function loadActiveId(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACTIVE_KEY);
}

export function saveActiveId(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) window.localStorage.setItem(ACTIVE_KEY, id);
  else window.localStorage.removeItem(ACTIVE_KEY);
}