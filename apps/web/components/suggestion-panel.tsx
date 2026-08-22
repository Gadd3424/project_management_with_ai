"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Sparkles, X } from "lucide-react";
import { api } from "@/lib/api";
import type { Suggestion, Task } from "@/lib/types";

export function SuggestionPanel({ task, organizationId, csrfToken, onClose }: {
  task: Task; organizationId: string; csrfToken: string; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: ["suggestions", task.id],
    queryFn: () => api<Suggestion[]>(`/tasks/${task.id}/suggestions`, { organizationId }),
  });
  const generate = useMutation({
    mutationFn: () => api<Suggestion[]>(`/tasks/${task.id}/suggestions/generate`, { method: "POST", organizationId, csrfToken }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suggestions", task.id] }),
  });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "accept" | "reject" }) =>
      api<Suggestion>(`/suggestions/${id}/${decision}`, { method: "POST", body: "{}", organizationId, csrfToken }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["suggestions", task.id] }),
  });
  return (
    <aside className="fixed inset-y-0 right-0 z-20 w-full max-w-xl overflow-y-auto border-l border-slate-200 bg-slate-50 p-6 shadow-2xl" aria-label="AI提案">
      <div className="mb-6 flex items-start justify-between"><div><p className="flex items-center gap-2 text-sm font-medium text-blue-600"><Sparkles className="size-4" />AI提案</p><h2 className="mt-1 text-xl font-semibold">{task.title}</h2></div><button className="button-secondary px-3" onClick={onClose} aria-label="閉じる"><X className="size-4" /></button></div>
      <button className="button-primary mb-6" onClick={() => generate.mutate()} disabled={generate.isPending}>提案を生成</button>
      {(generate.error || query.error) && <p role="alert" className="mb-4 text-red-600">{String(generate.error ?? query.error)}</p>}
      <div className="space-y-4">
        {query.data?.map((item) => <article key={item.id} className="card p-5">
          <div className="flex items-center justify-between gap-4"><span className="text-sm font-medium text-blue-700">{item.suggestion_type === "delay_risk" ? "期限遅延リスク" : "次のアクション"}</span><span className="rounded-full bg-blue-50 px-3 py-1 text-sm font-medium text-blue-800">確信度 {Math.round(item.confidence * 100)}%</span></div>
          <p className="mt-4 font-medium">{item.suggestion_type === "delay_risk" ? (item.content.data_sufficient ? `遅延確率 ${Math.round(Number(item.content.delay_probability) * 100)}%` : "データ不足") : String(item.content.action)}</p>
          <h3 className="mt-4 text-sm font-medium">根拠</h3><p className="mt-1 text-sm leading-6 text-slate-600">{item.rationale}</p>
          <h3 className="mt-4 text-sm font-medium">想定効果</h3><p className="mt-1 text-sm text-slate-600">{item.expected_effect}</p>
          {item.risks.length > 0 && <div className="mt-4 flex gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900"><AlertTriangle className="mt-0.5 size-4 shrink-0" />{item.risks[0]}</div>}
          <p className="mt-3 text-xs text-slate-500">参照元 {item.references.length}件 · 推論 {item.inference_ms}ms · 状態 {item.decision}</p>
          {item.decision === "pending" && <div className="mt-5 flex gap-2"><button className="button-primary" onClick={() => decide.mutate({ id: item.id, decision: "accept" })}><Check className="size-4" />採用</button><button className="button-secondary" onClick={() => decide.mutate({ id: item.id, decision: "reject" })}><X className="size-4" />却下</button></div>}
        </article>)}
        {query.data?.length === 0 && <p className="text-sm text-slate-500">まだ提案はありません。</p>}
      </div>
    </aside>
  );
}

