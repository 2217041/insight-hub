"use client";

import type { Conversation } from "@/lib/types";

type Props = {
  conversations: Conversation[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
  onDelete: (id: string) => void;
};

export function Sidebar({
  conversations,
  activeId,
  onSelect,
  onNew,
  onDelete,
}: Props) {
  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50/60">
      <div className="flex items-center justify-between px-4 py-4">
        <span className="text-sm font-semibold text-gray-800">Insight Hub</span>
        <button
          onClick={onNew}
          className="rounded-md bg-gray-900 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-gray-700"
          title="新建对话"
        >
          + 新对话
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2 pb-4">
        {conversations.length === 0 ? (
          <p className="px-2 py-8 text-center text-xs text-gray-400">
            还没有对话
            <br />
            点右上角「新对话」开始
          </p>
        ) : (
          <ul className="space-y-0.5">
            {conversations.map((c) => {
              const active = c.id === activeId;
              return (
                <li key={c.id} className="group relative">
                  <button
                    onClick={() => onSelect(c.id)}
                    className={`w-full truncate rounded-md px-3 py-2 pr-8 text-left text-sm transition ${
                      active
                        ? "bg-white text-gray-900 shadow-sm ring-1 ring-gray-200"
                        : "text-gray-600 hover:bg-white/70"
                    }`}
                  >
                    {c.title}
                  </button>
                  <button
                    onClick={() => onDelete(c.id)}
                    className="absolute top-1/2 right-1.5 -translate-y-1/2 rounded p-1 text-xs text-gray-400 opacity-0 transition group-hover:opacity-100 hover:bg-red-50 hover:text-red-600"
                    title="删除对话"
                  >
                    ✕
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-gray-200 px-4 py-3 text-[11px] leading-relaxed text-gray-400">
        W2 · 骨架阶段
        <br />
        历史存在浏览器 localStorage
      </div>
    </aside>
  );
}