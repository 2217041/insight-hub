"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { getAccessToken } from "@/lib/auth";

type Doc = {
  id: string;
  name: string;
  size_bytes: number;
  status: string;
  progress: number;
  chunk_count: number;
  error_reason?: string | null;
  created_at: string;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

const STATUS_TEXT: Record<string, string> = {
  pending: "排队中",
  parsing: "解析中",
  chunking: "分块中",
  ready: "已完成",
  failed: "失败",
};

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [cached, setCached] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const authHeaders = useCallback((): HeadersInit => {
    const token = getAccessToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/documents`, { headers: authHeaders() });
      if (res.status === 401) {
        setError("登录已过期，请重新登录");
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { items: Doc[]; cached: boolean };
      setDocs(data.items);
      setCached(data.cached);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [authHeaders]);

  // 挂载后拉一次列表。这是"从外部系统（后端）同步状态"的典型场景，
  // 规则建议的写法（在渲染期读数据）在这里不适用，显式豁免。
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    void load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  // 有文档还没处理完时，每 1.5 秒刷新一次（简单可靠；SSE 版本见 /api/documents/{id}/progress）
  useEffect(() => {
    const busy = docs.some((d) => !["ready", "failed"].includes(d.status));
    if (!busy) return;
    const timer = setInterval(() => void load(), 1500);
    return () => clearInterval(timer);
  }, [docs, load]);

  async function upload(file: File) {
    setUploading(true);
    setError(null);
    try {
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${API_BASE}/api/documents`, {
        method: "POST",
        headers: authHeaders(),
        body: form,
      });
      const body = await res.json();
      if (!res.ok) {
        throw new Error(body?.message ?? `上传失败（HTTP ${res.status}）`);
      }
      if (body.deduplicated) {
        setError("这个文件之前上传过（内容相同），已复用原记录，不会重复解析。");
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "上传失败");
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  }

  return (
    <main className="mx-auto min-h-screen max-w-3xl px-6 py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">知识库文档</h1>
          <p className="mt-1 text-sm text-gray-500">
            上传后进入异步管道：解析 → 分块 → 就绪（W10 接入向量化）
          </p>
        </div>
        <Link href="/" className="text-sm text-emerald-700 hover:underline">
          ← 回到对话
        </Link>
      </header>

      <section className="mb-6 rounded-xl border border-dashed border-gray-300 bg-gray-50/60 p-6 text-center">
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,.markdown,.pdf"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void upload(f);
          }}
        />
        <button
          onClick={() => fileRef.current?.click()}
          disabled={uploading}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-emerald-500 disabled:bg-gray-300"
        >
          {uploading ? "上传中…" : "选择文件上传"}
        </button>
        <p className="mt-2 text-xs text-gray-400">
          支持 .md / .txt（PDF 解析在 W10 实现），单文件 ≤ 20 MB
        </p>
      </section>

      {error && (
        <p className="mb-4 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">{error}</p>
      )}

      <section className="rounded-xl border border-gray-200 bg-white">
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-3">
          <span className="text-xs text-gray-500">
            共 {docs.length} 个文档{cached ? "（来自缓存）" : ""}
          </span>
          <button onClick={() => void load()} className="text-xs text-gray-500 hover:text-gray-900">
            刷新
          </button>
        </div>

        {loading ? (
          <div className="space-y-2 p-4">
            {[0, 1, 2].map((i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-gray-100" />
            ))}
          </div>
        ) : docs.length === 0 ? (
          <p className="px-4 py-12 text-center text-sm text-gray-400">
            还没有文档，先上传一个试试
          </p>
        ) : (
          <ul className="divide-y divide-gray-100">
            {docs.map((d) => (
              <li key={d.id} className="px-4 py-3">
                <div className="flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm text-gray-800">{d.name}</p>
                    <p className="mt-0.5 text-xs text-gray-400">
                      {fmtSize(d.size_bytes)} · {d.chunk_count} 块
                      {d.error_reason ? ` · ${d.error_reason}` : ""}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${
                      d.status === "ready"
                        ? "bg-emerald-50 text-emerald-700"
                        : d.status === "failed"
                          ? "bg-red-50 text-red-700"
                          : "bg-amber-50 text-amber-700"
                    }`}
                  >
                    {STATUS_TEXT[d.status] ?? d.status}
                  </span>
                </div>

                {!["ready", "failed"].includes(d.status) && (
                  <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-gray-100">
                    <div
                      className="h-full rounded-full bg-emerald-500 transition-all"
                      style={{ width: `${Math.max(d.progress, 5)}%` }}
                    />
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </main>
  );
}