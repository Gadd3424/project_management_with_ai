"use client";

import { Sparkles } from "lucide-react";
import type { Task } from "@/lib/types";

const columns = [
  ["todo", "未着手"], ["in_progress", "進行中"], ["review", "レビュー"], ["done", "完了"],
] as const;

export function Kanban({ tasks, onSuggest }: { tasks: Task[]; onSuggest: (task: Task) => void }) {
  return <div className="grid gap-4 xl:grid-cols-4">{columns.map(([status, label]) => <section key={status} aria-labelledby={`column-${status}`}>
    <div className="mb-3 flex items-center justify-between"><h2 id={`column-${status}`} className="font-medium">{label}</h2><span className="text-sm text-slate-500">{tasks.filter((t) => t.status === status).length}</span></div>
    <div className="space-y-3">{tasks.filter((task) => task.status === status).map((task) => <article key={task.id} className="card p-4">
      <div className="flex items-start justify-between gap-2"><h3 className="font-medium leading-6">{task.title}</h3><span className="text-xs text-slate-500">{task.priority}</span></div>
      <p className="mt-2 line-clamp-2 text-sm text-slate-600">{task.description || "説明なし"}</p>
      <div className="mt-4 flex items-center justify-between"><span className="text-xs text-slate-500">{task.due_at ? new Date(task.due_at).toLocaleDateString("ja-JP") : "期限なし"}</span><button className="button-secondary px-3 py-1.5 text-sm" onClick={() => onSuggest(task)}><Sparkles className="size-4" />AI提案</button></div>
    </article>)}</div>
  </section>)}</div>;
}

