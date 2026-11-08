"use client";

/**
 * 鉴权相关的客户端封装。
 *
 * 类型来自 OpenAPI 自动生成（types/api.d.ts）——后端改字段，这里会编译报错。
 * 这就是"契约先行"的实际收益，不用手写 interface 再对一遍。
 */

import type { components } from "@/types/api";

export type UserResponse = components["schemas"]["UserResponse"];
export type TokenResponse = components["schemas"]["TokenResponse"];

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";
const ACCESS_KEY = "insight-hub:access";
const REFRESH_KEY = "insight-hub:refresh";

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function saveTokens(t: TokenResponse): void {
  window.localStorage.setItem(ACCESS_KEY, t.access_token);
  window.localStorage.setItem(REFRESH_KEY, t.refresh_token);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

/** 统一把后端的错误体翻译成人能看的一句话。 */
async function toError(res: Response): Promise<Error> {
  try {
    const body = (await res.json()) as {
      code?: string;
      message?: string;
      request_id?: string;
    };
    const rid = body.request_id ? `（${body.request_id}）` : "";
    return new Error(`${body.message ?? `HTTP ${res.status}`}${rid}`);
  } catch {
    return new Error(`HTTP ${res.status}`);
  }
}

async function post<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw await toError(res);
  return (await res.json()) as T;
}

export async function login(email: string, password: string): Promise<void> {
  const t = await post<TokenResponse>("/api/auth/login", { email, password });
  saveTokens(t);
}

export async function register(
  email: string,
  password: string,
  name: string,
): Promise<void> {
  await post<UserResponse>("/api/auth/register", { email, password, name });
  await login(email, password);
}

/**
 * 拉当前用户。
 *
 * access token 过期时自动用 refresh 换一次——这就是"短 access + 长 refresh"的意义：
 * 用户不用重新登录，但泄露的 access 只有 15 分钟价值。
 */
export async function fetchMe(): Promise<UserResponse | null> {
  const token = getAccessToken();
  if (!token) return null;

  const call = async (t: string) =>
    fetch(`${API_BASE}/api/auth/me`, {
      headers: { Authorization: `Bearer ${t}` },
    });

  let res = await call(token);

  if (res.status === 401) {
    const refresh = getRefreshToken();
    if (!refresh) {
      clearTokens();
      return null;
    }
    try {
      const t = await post<TokenResponse>("/api/auth/refresh", {
        refresh_token: refresh,
      });
      saveTokens(t);
      res = await call(t.access_token);
    } catch {
      clearTokens();
      return null;
    }
  }

  if (!res.ok) return null;
  return (await res.json()) as UserResponse;
}

export function logout(): void {
  clearTokens();
}