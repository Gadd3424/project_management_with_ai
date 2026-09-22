"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ListTodo, MessageCircle, UserPlus, Users } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { LoginForm } from "@/components/login-form";
import { ProjectDialog } from "@/components/project-dialog";
import { ProjectSidebar } from "@/components/project-sidebar";
import { api } from "@/lib/api";
import type { Project, ProjectMember, ProjectMessage, ProjectSummary, Task } from "@/lib/types";
import { useWorkspace } from "@/lib/use-workspace";

export default function ProjectPage() {
  const projectId = String(useParams().projectId);
  const workspace = useWorkspace();
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const enabled = !!workspace.organizationId;
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => api<Project>(`/projects/${projectId}`, { organizationId: workspace.organizationId }),
    enabled,
  });
  const dashboard = useQuery({
    queryKey: ["project-dashboard", workspace.organizationId],
    queryFn: () => api<ProjectSummary[]>("/project-dashboard", { organizationId: workspace.organizationId }),
    enabled,
  });
  const members = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => api<ProjectMember[]>(`/projects/${projectId}/members`, { organizationId: workspace.organizationId }),
    enabled,
  });
  const tasks = useQuery({
    queryKey: ["tasks", projectId],
    queryFn: () => api<Task[]>(`/projects/${projectId}/tasks`, { organizationId: workspace.organizationId }),
    enabled,
  });
  const messages = useQuery({
    queryKey: ["project-messages", projectId],
    queryFn: () => api<{ items: ProjectMessage[] }>(`/projects/${projectId}/messages?limit=5`, { organizationId: workspace.organizationId }),
    enabled,
  });
  const summary = dashboard.data?.find((item) => item.id === projectId);
  const role = summary?.my_role ?? "viewer";
  const organizationRole = workspace.organizations.data?.find((item) => item.id === workspace.organizationId)?.role;
  const canManageMembers = organizationRole === "owner" || organizationRole === "admin";
  const closeEditor = () => router.replace(`/projects/${projectId}`);

  if (!workspace.authenticated) {
    return <LoginForm onLogin={(csrf) => { workspace.setCsrfToken(csrf); workspace.setAuthenticated(true); }} />;
  }

  return <div className="flex min-h-screen bg-slate-50">
    <ProjectSidebar projectId={projectId} role={role} />
    <main className="min-w-0 flex-1 p-6 lg:p-8">
      <div className="mb-7"><p className="text-sm text-slate-500">プロジェクト概要</p><h1 className="text-3xl font-semibold">{project.data?.name}</h1><p className="mt-2 text-slate-600">{project.data?.description}</p></div>
      <div className="grid gap-5 lg:grid-cols-3">
        <section className="card p-5 lg:col-span-2"><h2 className="font-semibold">目的と成功条件</h2><dl className="mt-4 space-y-4 text-sm"><div><dt className="text-slate-500">目的</dt><dd className="mt-1 whitespace-pre-wrap">{project.data?.objective || "未設定"}</dd></div><div><dt className="text-slate-500">成功条件</dt><dd className="mt-1 whitespace-pre-wrap">{project.data?.success_criteria || "未設定"}</dd></div></dl></section>
        <section className="card p-5"><h2 className="font-semibold">進捗</h2><p className="mt-4 text-3xl font-semibold">{Math.round((summary?.completion_rate ?? 0) * 100)}%</p><p className="text-sm text-slate-500">全{summary?.task_count ?? tasks.data?.length ?? 0}タスク</p><Link href={`/projects/${projectId}/tasks`} className="button-primary mt-4"><ListTodo className="size-4" />タスクを開く</Link></section>
        <section className="card p-5 lg:col-span-2"><div className="flex items-center justify-between"><h2 className="flex items-center gap-2 font-semibold"><Users className="size-4" />参加ユーザー</h2>{canManageMembers && <Link href={`/projects/${projectId}/members`} className="button-secondary"><UserPlus className="size-4" />招待・管理</Link>}</div><div className="mt-4 grid gap-3 sm:grid-cols-2">{members.data?.slice(0, 6).map((member) => <div key={member.id} className="rounded-lg bg-slate-50 p-3"><p className="font-medium">{member.display_name}</p><p className="text-xs text-slate-500">{member.invitation_status === "pending" ? "招待中" : member.role === "project_admin" ? "管理者" : member.role === "editor" ? "編集者" : "閲覧者"}</p></div>)}</div></section>
        <section className="card p-5"><div className="flex items-center justify-between"><h2 className="flex items-center gap-2 font-semibold"><MessageCircle className="size-4" />最近のチャット</h2><Link href={`/projects/${projectId}/chat`} className="text-sm text-blue-700">開く</Link></div><div className="mt-4 space-y-3">{messages.data?.items.slice(-3).map((message) => <div key={message.id}><p className="text-xs text-slate-500">{message.author_name}</p><p className="line-clamp-2 text-sm">{message.body}</p></div>)}{!messages.data?.items.length && <p className="text-sm text-slate-500">メッセージはありません。</p>}</div></section>
      </div>
    </main>
    {searchParams.get("edit") === "1" && project.data && <ProjectDialog project={project.data} organizationId={workspace.organizationId} csrfToken={workspace.csrfToken} onClose={closeEditor} onSaved={async () => { closeEditor(); await Promise.all([queryClient.invalidateQueries({ queryKey: ["project", projectId] }), queryClient.invalidateQueries({ queryKey: ["project-dashboard"] })]); }} onDeleted={() => router.push("/")} />}
  </div>;
}
