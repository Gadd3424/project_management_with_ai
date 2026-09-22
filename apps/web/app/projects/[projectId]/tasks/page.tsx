"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { useParams } from "next/navigation";
import { useState } from "react";
import { Kanban } from "@/components/kanban";
import { LoginForm } from "@/components/login-form";
import { ProjectSidebar } from "@/components/project-sidebar";
import { SuggestionPanel } from "@/components/suggestion-panel";
import { TaskDialog } from "@/components/task-dialog";
import { api } from "@/lib/api";
import type { Project, ProjectSummary, Task, TaskStatus } from "@/lib/types";
import { useWorkspace } from "@/lib/use-workspace";

export default function TasksPage() {
  const projectId = String(useParams().projectId);
  const workspace = useWorkspace(); const queryClient = useQueryClient();
  const [dialog, setDialog] = useState<Task | "new" | null>(null); const [suggestion, setSuggestion] = useState<Task | null>(null); const [error, setError] = useState("");
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api<Project>(`/projects/${projectId}`, { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId });
  const dashboard = useQuery({ queryKey: ["project-dashboard", workspace.organizationId], queryFn: () => api<ProjectSummary[]>("/project-dashboard", { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId });
  const tasks = useQuery({ queryKey: ["tasks", projectId], queryFn: () => api<Task[]>(`/projects/${projectId}/tasks`, { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId });
  const role = dashboard.data?.find((item) => item.id === projectId)?.my_role ?? "viewer"; const canEdit = role !== "viewer";
  const reorder = useMutation({ mutationFn: ({ updates }: { next: Task[]; updates: Task[] }) => api<Task[]>(`/projects/${projectId}/tasks/reorder`, { method: "PATCH", organizationId: workspace.organizationId, csrfToken: workspace.csrfToken, body: JSON.stringify({ tasks: updates.map(({ id, status, position, version }) => ({ id, status, position, version })) }) }), onMutate: async ({ next }) => { const previous = queryClient.getQueryData<Task[]>(["tasks", projectId]); queryClient.setQueryData(["tasks", projectId], next); return { previous }; }, onSuccess: (saved) => queryClient.setQueryData(["tasks", projectId], saved), onError: (reason, _v, context) => { if (context?.previous) queryClient.setQueryData(["tasks", projectId], context.previous); setError(reason instanceof Error ? reason.message : "タスクを移動できませんでした。"); } });
  const moveTask = (task: Task, status: TaskStatus, position: number) => { const current = tasks.data ?? []; const groups = new Map<TaskStatus, Task[]>(); for (const value of ["todo", "in_progress", "on_hold", "done"] as TaskStatus[]) groups.set(value, current.filter((item) => item.status === value && item.id !== task.id).sort((a, b) => a.position - b.position)); groups.get(status)!.splice(position, 0, { ...task, status }); const next = Array.from(groups.entries()).flatMap(([nextStatus, items]) => items.map((item, index) => ({ ...item, status: nextStatus, position: index }))); const updates = next.filter((item) => { const before = current.find((value) => value.id === item.id)!; return item.status !== before.status || item.position !== before.position; }); if (updates.length) reorder.mutate({ next, updates }); };
  if (!workspace.authenticated) return <LoginForm onLogin={(csrf) => { workspace.setCsrfToken(csrf); workspace.setAuthenticated(true); }} />;
  return <div className="flex min-h-screen bg-slate-50"><ProjectSidebar projectId={projectId} role={role} /><main className="min-w-0 flex-1 p-6 lg:p-8"><div className="mb-7 flex items-end justify-between gap-4"><div><p className="text-sm text-slate-500">タスク管理</p><h1 className="text-3xl font-semibold">{project.data?.name}</h1></div>{canEdit && <button className="button-primary" onClick={() => setDialog("new")}><Plus className="size-4" />タスクを追加</button>}</div>{error && <p className="mb-4 rounded-lg bg-red-50 p-3 text-red-700">{error}</p>}{tasks.isLoading ? <p>読み込み中…</p> : <Kanban tasks={tasks.data ?? []} canManage={canEdit} onEdit={(task) => setDialog(task)} onSuggest={setSuggestion} onMove={moveTask} />}</main>{dialog && <TaskDialog task={dialog === "new" ? undefined : dialog} projectId={projectId} organizationId={workspace.organizationId} csrfToken={workspace.csrfToken} onClose={() => setDialog(null)} />}{suggestion && <SuggestionPanel task={suggestion} organizationId={workspace.organizationId} csrfToken={workspace.csrfToken} onClose={() => setSuggestion(null)} />}</div>;
}
