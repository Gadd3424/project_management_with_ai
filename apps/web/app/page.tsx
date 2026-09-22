"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderKanban, LogOut, MessageCircle, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { LoginForm } from "@/components/login-form";
import { ProjectDialog } from "@/components/project-dialog";
import { api } from "@/lib/api";
import type { Project, ProjectMember, ProjectSummary } from "@/lib/types";
import { useWorkspace } from "@/lib/use-workspace";

export default function Home() {
  const workspace = useWorkspace();
  const queryClient = useQueryClient();
  const [creating, setCreating] = useState(false);
  const projects = useQuery({
    queryKey: ["project-dashboard", workspace.organizationId],
    queryFn: () => api<ProjectSummary[]>("/project-dashboard", { organizationId: workspace.organizationId }),
    enabled: !!workspace.organizationId,
  });
  const invitations = useQuery({
    queryKey: ["project-invitations", workspace.organizationId],
    queryFn: () => api<ProjectMember[]>("/project-invitations", { organizationId: workspace.organizationId }),
    enabled: !!workspace.organizationId,
  });
  const decide = useMutation({
    mutationFn: ({ invitation, decision }: { invitation: ProjectMember; decision: "accept" | "decline" }) => api<void>(`/project-invitations/${invitation.id}/${decision}`, { method: "POST", organizationId: workspace.organizationId, csrfToken: workspace.csrfToken, body: JSON.stringify({ version: invitation.version }) }),
    onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: ["project-invitations"] }), queryClient.invalidateQueries({ queryKey: ["project-dashboard"] })]); },
  });
  if (!workspace.authenticated) return <LoginForm onLogin={(csrf) => { workspace.setCsrfToken(csrf); workspace.setAuthenticated(true); }} />;
  const currentOrg = workspace.organizations.data?.find((item) => item.id === workspace.organizationId);
  const canCreate = currentOrg && currentOrg.role !== "viewer";
  return <main className="min-h-screen bg-slate-50">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white"><FolderKanban className="size-5" /></span><div><p className="font-semibold">Evolutionary Project AI</p><p className="text-xs text-slate-500">{workspace.user?.display_name}のワークスペース</p></div></div><div className="flex gap-2"><Link href="/admin/users" className="button-secondary"><Users className="size-4" />ユーザー管理</Link><button className="button-secondary" onClick={() => api("/auth/logout", { method: "POST", csrfToken: workspace.csrfToken }).finally(() => workspace.setAuthenticated(false))}><LogOut className="size-4" />ログアウト</button></div></div></header>
    <div className="mx-auto max-w-7xl px-6 py-8">
      <div className="mb-7 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-slate-500">{currentOrg?.name}</p><h1 className="mt-1 text-3xl font-semibold">参加プロジェクト</h1></div><div className="flex gap-2"><select className="field w-auto" value={workspace.organizationId} onChange={(e) => workspace.setOrganizationId(e.target.value)}>{workspace.organizations.data?.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select>{canCreate && <button className="button-primary" onClick={() => setCreating(true)}><Plus className="size-4" />新規プロジェクト</button>}</div></div>
      {!!invitations.data?.length && <section className="mb-8 rounded-xl border border-blue-200 bg-blue-50 p-5"><h2 className="font-semibold text-blue-900">プロジェクトへの招待</h2><div className="mt-3 space-y-2">{invitations.data.map((invitation) => <div key={invitation.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-white p-3"><div><p className="font-medium">プロジェクトへの参加依頼</p><p className="text-sm text-slate-600">役割: {invitation.role === "editor" ? "編集者" : "閲覧者"}</p></div><div className="flex gap-2"><button className="button-primary" onClick={() => decide.mutate({ invitation, decision: "accept" })}>参加</button><button className="button-secondary" onClick={() => decide.mutate({ invitation, decision: "decline" })}>辞退</button></div></div>)}</div></section>}
      {projects.isLoading ? <p>プロジェクトを読み込んでいます…</p> : projects.data?.length ? <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">{projects.data.map((project) => <Link href={`/projects/${project.id}`} key={project.id} className="card block p-5 transition hover:-translate-y-0.5 hover:shadow-md"><div className="flex items-start justify-between gap-3"><h2 className="text-lg font-semibold">{project.name}</h2><span className="rounded-full bg-slate-100 px-2 py-1 text-xs">{project.my_role === "project_admin" ? "管理者" : project.my_role === "editor" ? "編集者" : "閲覧者"}</span></div><p className="mt-2 line-clamp-2 text-sm text-slate-600">{project.description || "概要なし"}</p><div className="mt-5 grid grid-cols-2 gap-3 text-sm"><div><span className="text-slate-500">タスク</span><p className="font-medium">{project.task_count}件・完了 {Math.round(project.completion_rate * 100)}%</p></div><div><span className="text-slate-500">進行中</span><p className="font-medium">{project.status_counts.in_progress ?? 0}件</p></div></div>{project.unread_count > 0 && <p className="mt-4 flex items-center gap-2 text-sm font-medium text-blue-700"><MessageCircle className="size-4" />未読メッセージ {project.unread_count}件</p>}</Link>)}</div> : <div className="card p-10 text-center"><h2 className="text-xl font-semibold">参加中のプロジェクトはありません</h2><p className="mt-2 text-slate-600">招待を承認するか、新しいプロジェクトを作成してください。</p></div>}
    </div>
    {creating && <ProjectDialog organizationId={workspace.organizationId} csrfToken={workspace.csrfToken} onClose={() => setCreating(false)} onSaved={async (_saved: Project) => { setCreating(false); await queryClient.invalidateQueries({ queryKey: ["project-dashboard"] }); }} onDeleted={() => undefined} />}
  </main>;
}
