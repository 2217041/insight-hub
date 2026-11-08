"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { login, register } from "@/lib/auth";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password, name);
      }
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-gray-50 px-6">
      <div className="w-full max-w-sm">
        <h1 className="text-center text-xl font-semibold text-gray-900">
          Insight Hub
        </h1>
        <p className="mt-1 mb-6 text-center text-sm text-gray-500">
          {mode === "login" ? "登录以继续" : "创建一个账号"}
        </p>

        <form
          onSubmit={submit}
          className="rounded-xl border border-gray-200 bg-white p-6 shadow-sm"
        >
          {mode === "register" && (
            <label className="mb-3 block">
              <span className="mb-1 block text-xs text-gray-500">昵称（可选）</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
                placeholder="怎么称呼你"
              />
            </label>
          )}

          <label className="mb-3 block">
            <span className="mb-1 block text-xs text-gray-500">邮箱</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
              placeholder="you@example.com"
            />
          </label>

          <label className="mb-4 block">
            <span className="mb-1 block text-xs text-gray-500">
              密码{mode === "register" && "（至少 8 位）"}
            </span>
            <input
              type="password"
              required
              minLength={mode === "register" ? 8 : 1}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-200 px-3 py-2 text-sm outline-none focus:border-gray-400"
              placeholder="••••••••"
            />
          </label>

          {error && (
            <p className="mb-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-emerald-600 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:bg-gray-300"
          >
            {loading ? "处理中…" : mode === "login" ? "登录" : "注册并登录"}
          </button>
        </form>

        <p className="mt-4 text-center text-xs text-gray-500">
          {mode === "login" ? "还没有账号？" : "已有账号？"}{" "}
          <button
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
            className="font-medium text-emerald-700 underline-offset-2 hover:underline"
          >
            {mode === "login" ? "去注册" : "去登录"}
          </button>
        </p>

        <p className="mt-6 text-center text-[11px] text-gray-400">
          W3 阶段 token 存在 localStorage，W4 会换成 httpOnly Cookie
        </p>
      </div>
    </main>
  );
}