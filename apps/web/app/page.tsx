"use client";

import { useCallback, useEffect, useState } from "react";

type Health = {
  status: string;
  db: string;
  db_detail?: string;
  redis: string;
  redis_detail?: string;
  version: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

function Row({
  label,
  value,
  detail,
}: {
  label: string;
  value: string;
  detail?: string;
}) {
  const ok = value === "ok";
  return (
    <div className="flex items-start justify-between gap-4 border-b border-gray-100 py-3 last:border-0">
      <span className="text-sm text-gray-500">{label}</span>
      <span className="text-right">
        <span
          className={`font-mono text-sm font-medium ${ok ? "text-emerald-600" : "text-red-600"}`}
        >
          {value}
        </span>
        {detail ? (
          <span className="block text-xs text-gray-400">{detail}</span>
        ) : null}
      </span>
    </div>
  );
}

export default function Home() {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setHealth((await res.json()) as Health);
    } catch (err) {
      setHealth(null);
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const allGreen =
    health?.status === "ok" && health?.db === "ok" && health?.redis === "ok";

  return (
    <main className="mx-auto flex min-h-screen w-full max-w-2xl flex-col justify-center px-6 py-16">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight text-gray-900">
          Insight Hub
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          多租户企业知识库 + AI Agent 工作台 · W1 链路自检
        </p>
      </header>

      <section className="rounded-xl border border-gray-200 p-6 shadow-sm">
        <div className="mb-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className={`h-2.5 w-2.5 rounded-full ${
                loading
                  ? "animate-pulse bg-gray-300"
                  : allGreen
                    ? "bg-emerald-500"
                    : "bg-red-500"
              }`}
            />
            <span className="text-sm font-medium text-gray-700">
              {loading
                ? "检测中…"
                : allGreen
                  ? "全部正常"
                  : "存在异常"}
            </span>
          </div>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="rounded-md border border-gray-200 px-3 py-1 text-xs text-gray-600 transition hover:bg-gray-50 disabled:opacity-50"
          >
            重新检测
          </button>
        </div>

        {loading ? (
          <div className="space-y-3 py-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-9 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : error ? (
          <div className="rounded-lg bg-red-50 p-4">
            <p className="text-sm font-medium text-red-700">后端不可达</p>
            <p className="mt-1 text-xs text-red-600">{error}</p>
            <p className="mt-2 text-xs text-red-500">
              确认 {API_BASE} 上 uvicorn 正在运行：
              <code className="ml-1 rounded bg-red-100 px-1">
                .venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
              </code>
            </p>
          </div>
        ) : health ? (
          <div>
            <Row label="服务状态" value={health.status} />
            <Row label="PostgreSQL" value={health.db} detail={health.db_detail} />
            <Row label="Redis" value={health.redis} detail={health.redis_detail} />
            <Row label="API 版本" value={health.version} />
          </div>
        ) : null}
      </section>

      <p className="mt-6 text-xs text-gray-400">
        下一步（W2）：把这张页面换成对话页骨架 —— 登录态、会话列表、流式输出。
      </p>
    </main>
  );
}