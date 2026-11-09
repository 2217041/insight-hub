import type { Conversation } from "./types";

/**
 * W2 阶段的持久化方案：localStorage。
 *
 * **W4 补充：必须按用户命名空间隔离。**
 * 之前的 key 是全局的（`insight-hub:conversations:v1`），导致换个账号登录
 * 看到的还是上一个账号的会话——因为数据根本不在后端，全在这台浏览器里。
 *
 * 现在的 key：`insight-hub:conversations:v1:<userId>`
 * 这是**临时方案**：真正的解法是把会话落库（W5 接后端），
 * 那时 localStorage 只留草稿态。
 */

const KEY_PREFIX = "insight-hub:conversations:v1";
const ACTIVE_PREFIX = "insight-hub:active:v1";
/** W2/W3 时期的全局 key，用于一次性迁移 */
const LEGACY_KEY = KEY_PREFIX;
const LEGACY_ACTIVE_KEY = ACTIVE_PREFIX;

function convKey(userId: string): string {
  return `${KEY_PREFIX}:${userId}`;
}

function activeKey(userId: string): string {
  return `${ACTIVE_PREFIX}:${userId}`;
}

/** 把旧版全局数据搬到该用户名下，搬完删除，避免二次迁移。 */
function migrateLegacy(userId: string): void {
  const legacy = window.localStorage.getItem(LEGACY_KEY);
  if (!legacy) return;
  const target = convKey(userId);
  if (!window.localStorage.getItem(target)) {
    window.localStorage.setItem(target, legacy);
  }
  window.localStorage.removeItem(LEGACY_KEY);
  window.localStorage.removeItem(LEGACY_ACTIVE_KEY);
}

export function loadConversations(userId: string): Conversation[] {
  if (typeof window === "undefined" || !userId) return [];
  try {
    migrateLegacy(userId);
    const raw = window.localStorage.getItem(convKey(userId));
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

export function saveConversations(userId: string, list: Conversation[]): void {
  if (typeof window === "undefined" || !userId) return;
  try {
    window.localStorage.setItem(convKey(userId), JSON.stringify(list));
  } catch {
    // 配额满或隐私模式：静默失败，不影响使用
  }
}

export function loadActiveId(userId: string): string | null {
  if (typeof window === "undefined" || !userId) return null;
  return window.localStorage.getItem(activeKey(userId));
}

export function saveActiveId(userId: string, id: string | null): void {
  if (typeof window === "undefined" || !userId) return;
  if (id) window.localStorage.setItem(activeKey(userId), id);
  else window.localStorage.removeItem(activeKey(userId));
}

/** 退出登录时清掉该用户的本地缓存（可选：保留也行，下次登录还能看到）。 */
export function clearUserCache(userId: string): void {
  if (typeof window === "undefined" || !userId) return;
  window.localStorage.removeItem(convKey(userId));
  window.localStorage.removeItem(activeKey(userId));
}