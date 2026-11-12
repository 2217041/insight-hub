"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { getAccessToken } from "@/lib/auth";

type Chunk = {
  id: string;
  parent_id: string | null;
  content: string;
  page: number;
  section_path: string;
  token_count: number;
  content_type: string;
  order_index: number;
};

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://127.0.0.1:8000";

export default function DocumentChunksPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [chunks, setChunks] = useState<Chunk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = getAccessToken();
    if (!token) {
      router.push("/login");
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/api/documents/${params.id}/chunks`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as { items: Chunk[] };
      setChunks(data.items);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, [params.id, router]);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    void load();
  }, [load]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const parents = chunks.filter((c) => !c.parent_id);
  const children = chunks.filter((c) => c.parent_id);

  return (
    <main className="mx-auto min-h-screen max-w-4xl px-6 py-10">
      <header className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">分块预览</h1>
          <p className="mt-1 text-sm text-gray-500">
            父块 {parents.length} 个 · 子块 {children.length} 个（子块是检索单位，父块用于生成）
          </p>
        </div>
        <Link href="/documents" className="text-sm text-emerald-700 hover:underline">
          ← 返回文档
        </Link>
      </header>

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-gray-100" />
          ))}
        </div>
      ) : error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>
      ) : chunks.length === 0 ? (
        <p className="py-16 text-center text-sm text-gray-400">
          还没有块（可能还在解析中）
        </p>
      ) : (
        <ul className="space-y-3">
          {chunks.map((c) => (
            <li
              key={c.id}
              className={`rounded-xl border p-4 ${
                c.parent_id
                  ? "ml-6 border-gray-200 bg-white"
                  : "border-emerald-200 bg-emerald-50/40"
              }`}
            >
              <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] text-gray-500">
                <span
                  className={`rounded px-1.5 py-0.5 font-medium ${
                    c.parent_id ? "bg-gray-100 text-gray-600" : "bg-emerald-100 text-emerald-700"
                  }`}
                >
                  {c.parent_id ? "子块" : "父块"}
                </span>
                <span>#{c.order_index}</span>
                <span>第 {c.page} 页</span>
                <span>{c.token_count} tok</span>
                {c.content_type === "table" && (
                  <span className="rounded bg-amber-100 px-1.5 py-0.5 text-amber-700">表格</span>
                )}
                {c.section_path && <span className="truncate">· {c.section_path}</span>}
              </div>
              <p className="whitespace-pre-wrap break-words text-sm leading-relaxed text-gray-700">
                {c.content.length > 400 ? `${c.content.slice(0, 400)}…` : c.content}
              </p>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}