"use client";

import { useQuery } from "@tanstack/react-query";
import { FolderKanban, LogOut, Pencil, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Kanban } from "@/components/kanban";
import { LoginForm } from "@/components/login-form";
import { SuggestionPanel } from "@/components/suggestion-panel";
import { ProjectDialog } from "@/components/project-dialog";
import { api } from "@/lib/api";
import type { Organization, Project, Task } from "@/lib/types";

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [csrfToken, setCsrfToken] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [projectDialog, setProjectDialog] = useState<"create" | "edit" | null>(null);
  useEffect(() => {
    api("/auth/me").then(() => {
      const csrf = document.cookie.split("; ").find((row) => row.startsWith("csrf_token="))?.split("=")[1] ?? "";
      setCsrfToken(decodeURIComponent(csrf));
      setAuthenticated(true);
    }).catch(() => undefined);
  }, []);
  const organizations = useQuery({ queryKey: ["organizations"], queryFn: () => api<Organization[]>("/organizations"), enabled: authenticated });
  useEffect(() => { if (!organizationId && organizations.data?.[0]) setOrganizationId(organizations.data[0].id); }, [organizations.data, organizationId]);
  const projects = useQuery({ queryKey: ["projects", organizationId], queryFn: () => api<Project[]>("/projects", { organizationId }), enabled: !!organizationId });
  useEffect(() => { if (!projectId && projects.data?.[0]) setProjectId(projects.data[0].id); }, [projects.data, projectId]);
  const tasks = useQuery({ queryKey: ["tasks", projectId], queryFn: () => api<Task[]>(`/projects/${projectId}/tasks`, { organizationId }), enabled: !!projectId });
  if (!authenticated) return <LoginForm onLogin={(csrf) => { setCsrfToken(csrf); setAuthenticated(true); }} />;
  const currentProject = projects.data?.find((item) => item.id === projectId);
  const currentOrganization = organizations.data?.find((item) => item.id === organizationId);
  const canManageProjects = !!currentOrganization && currentOrganization.role !== "viewer";
  return <main className="min-h-screen">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white"><FolderKanban className="size-5" /></span><div><p className="font-semibold">Evolutionary Project AI</p><p className="text-xs text-slate-500">意思決定支援ワークスペース</p></div></div><div className="flex gap-2"><Link href="/admin/users" className="button-secondary"><Users className="size-4"/>ユーザー管理</Link><button className="button-secondary" onClick={() => api("/auth/logout", { method: "POST", csrfToken }).finally(() => setAuthenticated(false))}><LogOut className="size-4" />ログアウト</button></div></div></header>
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-slate-500">{currentOrganization?.name}</p><h1 className="mt-1 text-3xl font-semibold">{currentProject?.name ?? "プロジェクト"}</h1><p className="mt-2 text-slate-600">{currentProject?.description}</p></div><div className="flex flex-wrap gap-2">{canManageProjects && <button className="button-primary" onClick={() => setProjectDialog("create")}><Plus className="size-4" />新規プロジェクト</button>}{canManageProjects && currentProject && <button className="button-secondary" onClick={() => setProjectDialog("edit")}><Pencil className="size-4" />編集</button>}<select className="field w-auto" value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="プロジェクト選択"><option value="">選択してください</option>{projects.data?.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div></div>
      {!projects.isLoading && !projects.data?.length ? <div className="card p-10 text-center"><h2 className="text-xl font-semibold">プロジェクトがありません</h2><p className="mt-2 text-slate-600">最初のプロジェクトを作成して作業を始めましょう。</p>{canManageProjects && <button className="button-primary mt-4" onClick={() => setProjectDialog("create")}><Plus className="size-4" />新規プロジェクト</button>}</div> : tasks.isLoading ? <p>タスクを読み込んでいます…</p> : <Kanban tasks={tasks.data ?? []} onSuggest={setSelectedTask} />}
    </div>
    {selectedTask && <SuggestionPanel task={selectedTask} organizationId={organizationId} csrfToken={csrfToken} onClose={() => setSelectedTask(null)} />}
    {projectDialog && <ProjectDialog project={projectDialog === "edit" ? currentProject : undefined} organizationId={organizationId} csrfToken={csrfToken} onClose={() => setProjectDialog(null)} onSaved={(saved) => { setProjectId(saved.id); setProjectDialog(null); }} onDeleted={(deletedId) => { const remaining = projects.data?.filter((item) => item.id !== deletedId) ?? []; setProjectId(remaining[0]?.id ?? ""); setProjectDialog(null); }} />}
  </main>;
}

