"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2, X } from "lucide-react";
import { FormEvent, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Task } from "@/lib/types";

type FormState = {
  title: string; description: string; notes: string;
  priority: "low" | "medium" | "high" | "urgent"; due_at: string; assignee_id: string;
};
type Assignee = { id: string; display_name: string };

function initialForm(task?: Task): FormState {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    notes: task?.notes ?? "",
    priority: (task?.priority as FormState["priority"]) ?? "medium",
    due_at: task?.due_at?.slice(0, 10) ?? "",
    assignee_id: task?.assignee_id ?? "",
  };
}

export function TaskDialog({ task, projectId, organizationId, csrfToken, onClose }: {
  task?: Task; projectId: string; organizationId: string; csrfToken: string; onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState(() => initialForm(task));
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const idempotencyKey = useRef(crypto.randomUUID());
  const assignees = useQuery({
    queryKey: ["task-assignees", organizationId],
    queryFn: () => api<Assignee[]>("/task-assignees", { organizationId }),
  });
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["tasks", projectId] });
    onClose();
  };
  const save = useMutation({
    mutationFn: () => api<Task>(task ? `/tasks/${task.id}` : `/projects/${projectId}/tasks`, {
      method: task ? "PATCH" : "POST", organizationId, csrfToken,
      headers: task ? undefined : { "Idempotency-Key": idempotencyKey.current },
      body: JSON.stringify({
        ...form,
        due_at: form.due_at ? `${form.due_at}T23:59:59Z` : null,
        assignee_id: form.assignee_id || null,
        ...(task ? { version: task.version } : {}),
      }),
    }),
    onSuccess: refresh,
    onError: (reason) => setError(
      reason instanceof ApiError && reason.status === 409
        ? "他のユーザーがタスクを更新しました。一覧を再読み込みしてください。"
        : reason instanceof Error ? reason.message : "タスクを保存できませんでした。",
    ),
  });
  const remove = useMutation({
    mutationFn: () => api<void>(`/tasks/${task!.id}`, {
      method: "DELETE", organizationId, csrfToken,
      body: JSON.stringify({ version: task!.version }),
    }),
    onSuccess: refresh,
    onError: (reason) => setError(reason instanceof Error ? reason.message : "タスクを削除できませんでした。"),
  });
  const submit = (event: FormEvent) => { event.preventDefault(); setError(""); save.mutate(); };
  return <div className="fixed inset-0 z-40 grid place-items-center bg-slate-950/40 p-4">
    <section role="dialog" aria-modal="true" aria-labelledby="task-dialog-title" className="card max-h-[95vh] w-full max-w-2xl overflow-y-auto p-6">
      <div className="mb-5 flex items-center justify-between"><h2 id="task-dialog-title" className="text-xl font-semibold">{task ? "タスクを編集" : "タスクを追加"}</h2><button className="button-secondary px-3" onClick={onClose} aria-label="閉じる"><X className="size-4" /></button></div>
      <form className="space-y-4" onSubmit={submit}>
        <label className="block"><span className="label">タスク名 *</span><input className="field" required maxLength={300} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
        <label className="block"><span className="label">概要</span><textarea className="field min-h-24" maxLength={20000} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></label>
        <label className="block"><span className="label">補足事項</span><textarea className="field min-h-24" maxLength={20000} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} /></label>
        <div className="grid gap-4 sm:grid-cols-3">
          <label><span className="label">優先度</span><select className="field" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as FormState["priority"] })}><option value="low">低</option><option value="medium">中</option><option value="high">高</option><option value="urgent">緊急</option></select></label>
          <label><span className="label">担当者</span><select className="field" value={form.assignee_id} onChange={(e) => setForm({ ...form, assignee_id: e.target.value })}><option value="">未設定</option>{assignees.data?.map((assignee) => <option key={assignee.id} value={assignee.id}>{assignee.display_name}</option>)}</select></label>
          <label><span className="label">期限</span><input className="field" type="date" value={form.due_at} onChange={(e) => setForm({ ...form, due_at: e.target.value })} /></label>
        </div>
        {!task && <p className="text-sm text-slate-600">新規タスクは「未着手」で作成されます。</p>}
        {error && <p role="alert" className="text-sm text-red-700">{error}</p>}
        <div className="flex justify-end gap-2"><button type="button" className="button-secondary" onClick={onClose}>キャンセル</button><button className="button-primary" disabled={save.isPending}>{save.isPending ? "保存中…" : "保存"}</button></div>
      </form>
      {task && <div className="mt-8 border-t border-red-200 pt-5"><h3 className="font-semibold text-red-700">タスクを削除</h3>{confirmDelete ? <div className="mt-3 flex items-center justify-between gap-3"><p className="text-sm">この操作は一覧からタスクを削除します。</p><button className="button bg-red-600 text-white" disabled={remove.isPending} onClick={() => remove.mutate()}><Trash2 className="size-4" />削除する</button></div> : <button className="button-secondary mt-3 text-red-700" onClick={() => setConfirmDelete(true)}><Trash2 className="size-4" />削除を確認</button>}</div>}
    </section>
  </div>;
}
