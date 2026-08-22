"use client";

import { useQuery } from "@tanstack/react-query";
import { FolderKanban, LogOut, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Kanban } from "@/components/kanban";
import { LoginForm } from "@/components/login-form";
import { SuggestionPanel } from "@/components/suggestion-panel";
import { api } from "@/lib/api";
import type { Organization, Project, Task } from "@/lib/types";

export default function Home() {
  const [authenticated, setAuthenticated] = useState(false);
  const [csrfToken, setCsrfToken] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
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
  return <main className="min-h-screen">
    <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex max-w-[1600px] items-center justify-between px-6 py-4"><div className="flex items-center gap-3"><span className="grid size-9 place-items-center rounded-lg bg-blue-600 text-white"><FolderKanban className="size-5" /></span><div><p className="font-semibold">Evolutionary Project AI</p><p className="text-xs text-slate-500">意思決定支援ワークスペース</p></div></div><div className="flex gap-2"><Link href="/admin/users" className="button-secondary"><Users className="size-4"/>ユーザー管理</Link><button className="button-secondary" onClick={() => api("/auth/logout", { method: "POST", csrfToken }).finally(() => setAuthenticated(false))}><LogOut className="size-4" />ログアウト</button></div></div></header>
    <div className="mx-auto max-w-[1600px] px-6 py-8">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4"><div><p className="text-sm text-slate-500">{organizations.data?.find((o) => o.id === organizationId)?.name}</p><h1 className="mt-1 text-3xl font-semibold">{currentProject?.name ?? "プロジェクト"}</h1><p className="mt-2 text-slate-600">{currentProject?.description}</p></div><select className="field w-auto" value={projectId} onChange={(event) => setProjectId(event.target.value)} aria-label="プロジェクト選択">{projects.data?.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></div>
      {tasks.isLoading ? <p>タスクを読み込んでいます…</p> : <Kanban tasks={tasks.data ?? []} onSuggest={setSelectedTask} />}
    </div>
    {selectedTask && <SuggestionPanel task={selectedTask} organizationId={organizationId} csrfToken={csrfToken} onClose={() => setSelectedTask(null)} />}
  </main>;
}
