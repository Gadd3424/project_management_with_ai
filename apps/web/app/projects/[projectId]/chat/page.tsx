"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Send } from "lucide-react";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { LoginForm } from "@/components/login-form";
import { ProjectSidebar } from "@/components/project-sidebar";
import { api } from "@/lib/api";
import type { Project, ProjectMessage, ProjectSummary } from "@/lib/types";
import { useWorkspace } from "@/lib/use-workspace";

export default function ChatPage() {
  const projectId = String(useParams().projectId); const workspace = useWorkspace(); const queryClient = useQueryClient();
  const [body, setBody] = useState(""); const [error, setError] = useState("");
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => api<Project>(`/projects/${projectId}`, { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId });
  const dashboard = useQuery({ queryKey: ["project-dashboard", workspace.organizationId], queryFn: () => api<ProjectSummary[]>("/project-dashboard", { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId });
  const messages = useQuery({ queryKey: ["project-messages", projectId], queryFn: () => api<{ items: ProjectMessage[]; next_before: string | null }>(`/projects/${projectId}/messages?limit=100`, { organizationId: workspace.organizationId }), enabled: !!workspace.organizationId, refetchInterval: 3000 });
  useEffect(() => { if (workspace.organizationId && messages.data) api<void>(`/projects/${projectId}/messages/read`, { method: "POST", organizationId: workspace.organizationId, csrfToken: workspace.csrfToken, body: "{}" }).then(() => queryClient.invalidateQueries({ queryKey: ["project-dashboard"] })).catch(() => undefined); }, [messages.dataUpdatedAt, workspace.organizationId]);
  const send = useMutation({ mutationFn: () => api<ProjectMessage>(`/projects/${projectId}/messages`, { method: "POST", organizationId: workspace.organizationId, csrfToken: workspace.csrfToken, body: JSON.stringify({ body }) }), onSuccess: async () => { setBody(""); setError(""); await queryClient.invalidateQueries({ queryKey: ["project-messages", projectId] }); }, onError: (reason) => setError(reason instanceof Error ? reason.message : "送信できませんでした。") });
  const role = dashboard.data?.find((item) => item.id === projectId)?.my_role ?? "viewer";
  if (!workspace.authenticated) return <LoginForm onLogin={(csrf) => { workspace.setCsrfToken(csrf); workspace.setAuthenticated(true); }} />;
  const submit = (event: FormEvent) => { event.preventDefault(); if (body.trim()) send.mutate(); };
  return <div className="flex min-h-screen bg-slate-50"><ProjectSidebar projectId={projectId} role={role} /><main className="flex min-w-0 flex-1 flex-col p-6 lg:p-8"><div className="mb-5"><p className="text-sm text-slate-500">プロジェクトチャット</p><h1 className="text-3xl font-semibold">{project.data?.name}</h1></div><section className="card flex min-h-[65vh] flex-1 flex-col overflow-hidden"><div className="flex-1 space-y-4 overflow-y-auto p-5" aria-live="polite">{messages.data?.items.map((message) => { const mine = message.author_id === workspace.user?.id; return <div key={message.id} className={`flex ${mine ? "justify-end" : "justify-start"}`}><div className={`max-w-[80%] rounded-xl px-4 py-3 ${mine ? "bg-blue-600 text-white" : "bg-slate-100"}`}><p className={`text-xs ${mine ? "text-blue-100" : "text-slate-500"}`}>{mine ? "自分" : message.author_name}・{new Date(message.created_at).toLocaleString("ja-JP")}</p><p className="mt-1 whitespace-pre-wrap break-words text-sm">{message.body}</p></div></div>})}{!messages.data?.items.length && <p className="text-center text-sm text-slate-500">最初のメッセージを送信しましょう。</p>}</div><form onSubmit={submit} className="border-t p-4"><textarea className="field min-h-20" maxLength={5000} value={body} onChange={(e) => setBody(e.target.value)} placeholder="メッセージを入力" />{error && <p className="mt-2 text-sm text-red-700">{error}</p>}<div className="mt-2 flex justify-end"><button className="button-primary" disabled={send.isPending || !body.trim()}><Send className="size-4" />{send.isPending ? "送信中…" : "送信"}</button></div></form></section></main></div>;
}
