"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Sparkles, Trash2, X } from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Project, ProjectAISuggestion, TaskDraft } from "@/lib/types";

type FormState = {
  name: string; description: string; objective: string; success_criteria: string;
  start_date: string; due_date: string; status: "active" | "archived";
};

const emptyForm: FormState = {
  name: "", description: "", objective: "", success_criteria: "",
  start_date: "", due_date: "", status: "active",
};

function dateValue(value: string | null | undefined) {
  return value ? value.slice(0, 10) : "";
}

export function ProjectDialog({ project, organizationId, csrfToken, onClose, onSaved, onDeleted }: {
  project?: Project; organizationId: string; csrfToken: string; onClose: () => void;
  onSaved: (project: Project) => void; onDeleted: (projectId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<FormState>(emptyForm);
  const [suggestion, setSuggestion] = useState<ProjectAISuggestion | null>(null);
  const [taskSuggestion, setTaskSuggestion] = useState<ProjectAISuggestion | null>(null);
  const [initialTasks, setInitialTasks] = useState<TaskDraft[]>([]);
  const [error, setError] = useState("");
  const [deleteName, setDeleteName] = useState("");
  const [touched, setTouched] = useState<Set<keyof FormState>>(new Set());
  const idempotencyKey = useRef(crypto.randomUUID());
  useEffect(() => {
    if (project) {
      setForm({
        name: project.name, description: project.description, objective: project.objective,
        success_criteria: project.success_criteria, start_date: dateValue(project.start_date),
        due_date: dateValue(project.due_date), status: project.status as FormState["status"],
      });
    }
  }, [project]);

  const suggest = useMutation({
    mutationFn: () => project
      ? api<ProjectAISuggestion>(`/projects/${project.id}/ai/change-proposal`, {
          method: "POST", body: "{}", organizationId, csrfToken,
        })
      : api<ProjectAISuggestion>("/projects/ai/defaults", {
          method: "POST", body: JSON.stringify({ name: form.name }), organizationId, csrfToken,
        }),
    onSuccess: setSuggestion,
    onError: (reason) => setError(reason instanceof Error ? reason.message : "AI提案を生成できませんでした。"),
  });

  const suggestTasks = useMutation({
    mutationFn: () => api<ProjectAISuggestion>("/projects/ai/task-suggestions", {
      method: "POST", organizationId, csrfToken,
      body: JSON.stringify({
        ...form,
        start_date: form.start_date ? `${form.start_date}T00:00:00Z` : null,
        due_date: form.due_date ? `${form.due_date}T23:59:59Z` : null,
      }),
    }),
    onSuccess: (result) => {
      setTaskSuggestion(result);
      const proposed = (result.proposed_values as { tasks?: Array<Record<string, unknown>> }).tasks ?? [];
      setInitialTasks((current) => [
        ...current.filter((item) => item.source === "manual"),
        ...proposed.map((item) => ({
          client_id: crypto.randomUUID(), title: String(item.title ?? ""),
          description: String(item.description ?? ""), notes: String(item.notes ?? ""),
          priority: (item.priority ?? "medium") as TaskDraft["priority"],
          due_at: dateValue(item.due_at as string | null), source: "ai" as const, selected: true,
          rationale: String(item.rationale ?? ""), confidence: Number(item.confidence ?? 0),
          assumptions: Array.isArray(item.assumptions) ? item.assumptions.map(String) : [],
        })),
      ]);
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "初期タスクを提案できませんでした。"),
  });

  const save = useMutation({
    mutationFn: () => api<Project>(project ? `/projects/${project.id}` : "/projects", {
      method: project ? "PATCH" : "POST",
      organizationId,
      csrfToken,
      headers: project ? undefined : { "Idempotency-Key": idempotencyKey.current },
      body: JSON.stringify({
        ...form,
        start_date: form.start_date ? `${form.start_date}T00:00:00Z` : null,
        due_date: form.due_date ? `${form.due_date}T23:59:59Z` : null,
        ...(project ? { version: project.version } : {}),
        ai_suggestion_id: suggestion?.id ?? null,
        ...(!project ? {
          ai_task_suggestion_id: taskSuggestion?.id ?? null,
          initial_tasks: initialTasks.filter((item) => item.selected).map((item) => ({
            title: item.title, description: item.description, notes: item.notes,
            priority: item.priority, due_at: item.due_at ? `${item.due_at}T23:59:59Z` : null,
          })),
        } : {}),
      }),
    }),
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ["projects", organizationId] });
      onSaved(saved);
    },
    onError: (reason) => setError(
      reason instanceof ApiError && reason.status === 409
        ? "他のユーザーがプロジェクトを更新しました。画面を閉じて再読込してください。"
        : reason instanceof Error ? reason.message : "保存できませんでした。",
    ),
  });

  const remove = useMutation({
    mutationFn: () => api<void>(`/projects/${project!.id}`, {
      method: "DELETE", organizationId, csrfToken, body: JSON.stringify({ version: project!.version }),
    }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["projects", organizationId] });
      onDeleted(project!.id);
    },
    onError: (reason) => setError(reason instanceof Error ? reason.message : "削除できませんでした。"),
  });

  function applySuggestion() {
    if (!suggestion) return;
    const proposed = suggestion.proposed_values;
    const proposedValue = (key: keyof FormState, current: string) => {
      if (!project && touched.has(key)) return current;
      return proposed[key] == null ? current : String(proposed[key]);
    };
    setForm((current) => ({
      ...current,
      description: proposedValue("description", current.description),
      objective: proposedValue("objective", current.objective),
      success_criteria: proposedValue("success_criteria", current.success_criteria),
      start_date: dateValue(proposedValue("start_date", current.start_date)) || current.start_date,
      due_date: dateValue(proposedValue("due_date", current.due_date)) || current.due_date,
      status: proposedValue("status", current.status) as FormState["status"],
    }));
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setError("");
    save.mutate();
  }

  function updateField(key: keyof FormState, value: string) {
    setTouched((current) => new Set(current).add(key));
    setForm((current) => ({ ...current, [key]: value }));
  }

  function addManualTask() {
    setInitialTasks((current) => [...current, {
      client_id: crypto.randomUUID(), title: "", description: "", notes: "",
      priority: "medium", due_at: "", source: "manual", selected: true,
    }]);
  }

  function updateInitialTask(id: string, changes: Partial<TaskDraft>) {
    setInitialTasks((current) => current.map((item) => item.client_id === id ? { ...item, ...changes } : item));
  }

  const fields: Array<[keyof FormState, string, "input" | "textarea" | "date" | "select"]> = [
    ["name", "プロジェクト名", "input"], ["description", "概要", "textarea"],
    ["objective", "目的", "textarea"], ["success_criteria", "成功条件", "textarea"],
    ["start_date", "開始予定日", "date"], ["due_date", "完了予定日", "date"],
    ["status", "ステータス", "select"],
  ];

  return <div className="fixed inset-0 z-30 grid place-items-center bg-slate-950/40 p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="project-dialog-title" className="card max-h-[95vh] w-full max-w-3xl overflow-y-auto p-6">
      <div className="mb-5 flex items-center justify-between">
        <h2 id="project-dialog-title" className="text-xl font-semibold">{project ? "プロジェクトを編集" : "新規プロジェクト"}</h2>
        <button className="button-secondary px-3" onClick={onClose} aria-label="閉じる"><X className="size-4" /></button>
      </div>
      <form onSubmit={submit} className="space-y-4">
        {fields.map(([key, label, kind]) => <label key={key} className="block">
          <span className="label">{label}{key === "name" && " *"}</span>
          {kind === "textarea" ? <textarea className="field min-h-20" value={form[key]} onChange={(e) => updateField(key, e.target.value)} />
            : kind === "select" ? <select className="field" value={form.status} onChange={(e) => updateField("status", e.target.value)}><option value="active">進行中</option><option value="archived">アーカイブ</option></select>
            : <input className="field" type={kind === "date" ? "date" : "text"} required={key === "name"} maxLength={key === "name" ? 200 : undefined} value={form[key]} onChange={(e) => updateField(key, e.target.value)} />}
        </label>)}
        <button type="button" className="button-secondary" disabled={suggest.isPending || (!project && form.name.trim().length < 2)} onClick={() => suggest.mutate()}>
          <Sparkles className="size-4" />{suggest.isPending ? "AIが分析しています…" : project ? "現在の状況からAI変更案を生成" : "AIで入力案を生成"}
        </button>
        {suggestion && <div className="rounded-lg border border-blue-200 bg-blue-50 p-4" aria-live="polite">
          <div className="flex items-center justify-between"><strong>AI提案</strong><span className="text-sm">確信度 {Math.round(suggestion.confidence * 100)}%</span></div>
          <p className="mt-2 text-sm">{suggestion.rationale}</p>
          <p className="mt-2 text-xs text-slate-600">AIによる提案です。内容を確認してから反映してください。</p>
          <dl className="mt-3 space-y-2 text-sm">{Object.entries(suggestion.proposed_values).map(([key, value]) => <div key={key}><dt className="font-medium">{key}</dt><dd className="whitespace-pre-wrap text-slate-700">{project ? `現在: ${String(form[key as keyof FormState] ?? "")} → 提案: ` : ""}{String(value)}</dd></div>)}</dl>
          {suggestion.risks.map((risk) => <p key={risk} className="mt-2 text-sm text-amber-800">注意: {risk}</p>)}
          <button type="button" className="button-primary mt-3" onClick={applySuggestion}>提案をフォームへ反映</button>
        </div>}
        {!project && <div className="rounded-xl border border-slate-200 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2"><div><h3 className="font-semibold">初期タスク</h3><p className="mt-1 text-sm text-slate-600">AI提案を選択し、手動タスクと一緒に作成できます。</p></div><div className="flex gap-2"><button type="button" className="button-secondary" onClick={addManualTask}><Plus className="size-4" />手動で追加</button><button type="button" className="button-secondary" disabled={suggestTasks.isPending || !form.objective.trim() || !form.success_criteria.trim()} onClick={() => suggestTasks.mutate()}><Sparkles className="size-4" />{suggestTasks.isPending ? "提案中…" : "AIでタスクを提案"}</button></div></div>
          {taskSuggestion && <div className="mt-3 rounded-lg bg-blue-50 p-3 text-sm"><p>{taskSuggestion.rationale}</p><div className="mt-2 flex flex-wrap items-center justify-between gap-2"><p className="text-xs text-slate-600">{taskSuggestion.provider === "evolutionary_merge" ? `進化的マージモデル ${taskSuggestion.model_version}` : "フォールバック提案"}・確信度 {Math.round(taskSuggestion.confidence * 100)}%</p><div className="flex gap-2"><button type="button" className="button-secondary px-2 py-1 text-xs" onClick={() => setInitialTasks((current) => current.map((item) => item.source === "ai" ? { ...item, selected: true } : item))}>AI提案を全選択</button><button type="button" className="button-secondary px-2 py-1 text-xs" onClick={() => setInitialTasks((current) => current.map((item) => item.source === "ai" ? { ...item, selected: false } : item))}>AI提案を全解除</button></div></div></div>}
          {initialTasks.length > 0 && <div className="mt-4 space-y-3">{initialTasks.map((task, index) => <div key={task.client_id} className={`rounded-lg border p-3 ${task.selected ? "border-slate-200" : "border-slate-100 opacity-60"}`}>
            <div className="mb-3 flex items-center justify-between gap-2"><label className="flex items-center gap-2 text-sm font-medium">{task.source === "ai" && <input type="checkbox" checked={task.selected} onChange={(e) => updateInitialTask(task.client_id, { selected: e.target.checked })} />}{task.source === "ai" ? `AI提案 ${index + 1}` : `手動タスク ${index + 1}`}</label><button type="button" className="button-secondary px-2 py-1 text-red-700" onClick={() => setInitialTasks((current) => current.filter((item) => item.client_id !== task.client_id))}><Trash2 className="size-4" />削除</button></div>
            <div className="grid gap-3 sm:grid-cols-2"><label className="sm:col-span-2"><span className="label">タスク名 *</span><input className="field" required={task.selected} maxLength={300} value={task.title} onChange={(e) => updateInitialTask(task.client_id, { title: e.target.value })} /></label><label className="sm:col-span-2"><span className="label">概要</span><textarea className="field min-h-16" value={task.description} onChange={(e) => updateInitialTask(task.client_id, { description: e.target.value })} /></label><label className="sm:col-span-2"><span className="label">補足事項</span><textarea className="field min-h-16" value={task.notes} onChange={(e) => updateInitialTask(task.client_id, { notes: e.target.value })} /></label><label><span className="label">優先度</span><select className="field" value={task.priority} onChange={(e) => updateInitialTask(task.client_id, { priority: e.target.value as TaskDraft["priority"] })}><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="urgent">緊急</option></select></label><label><span className="label">期限</span><input className="field" type="date" value={task.due_at} onChange={(e) => updateInitialTask(task.client_id, { due_at: e.target.value })} /></label></div>
            {task.rationale && <p className="mt-2 text-xs text-slate-600">提案理由: {task.rationale}（確信度 {Math.round((task.confidence ?? 0) * 100)}%）</p>}
          </div>)}</div>}
        </div>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <div className="flex flex-wrap justify-end gap-2"><button type="button" className="button-secondary" onClick={onClose}>キャンセル</button><button className="button-primary" disabled={save.isPending}>{save.isPending ? "保存中…" : "保存"}</button></div>
      </form>
      {project && <div className="mt-8 border-t border-red-200 pt-5">
        <h3 className="font-semibold text-red-700">プロジェクトを削除</h3>
        <p className="mt-1 text-sm text-slate-600">確認のため「{project.name}」と入力してください。データは論理削除されます。</p>
        <div className="mt-3 flex gap-2"><input className="field" value={deleteName} onChange={(e) => setDeleteName(e.target.value)} aria-label="削除するプロジェクト名" /><button type="button" className="button bg-red-600 text-white hover:bg-red-700" disabled={deleteName !== project.name || remove.isPending} onClick={() => remove.mutate()}><Trash2 className="size-4" />削除</button></div>
      </div>}
    </section>
  </div>;
}
