"use client";

import { FolderKanban, LayoutDashboard, ListTodo, MessageCircle, Settings, Users, X, Menu } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

export function ProjectSidebar({ projectId, role }: { projectId: string; role: string }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const editable = role === "project_admin" || role === "editor";
  const manageable = role === "project_admin";
  const items = [
    ["/", "ユーザーTOP", LayoutDashboard, true],
    [`/projects/${projectId}`, "プロジェクト概要", FolderKanban, true],
    [`/projects/${projectId}/tasks`, "タスク管理", ListTodo, editable],
    [`/projects/${projectId}/chat`, "チャット", MessageCircle, true],
    [`/projects/${projectId}/members`, "メンバー管理", Users, manageable],
    [`/projects/${projectId}?edit=1`, "プロジェクト編集", Settings, manageable],
  ] as const;
  const menu = <aside className="flex h-full w-64 flex-col border-r border-slate-200 bg-white p-4"><div className="mb-5 flex items-center justify-between"><strong>プロジェクト</strong><button className="md:hidden" onClick={() => setOpen(false)} aria-label="メニューを閉じる"><X /></button></div><nav className="space-y-1">{items.filter(([, , , show]) => show).map(([href, label, Icon]) => <Link key={href} href={href} onClick={() => setOpen(false)} className={`flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${pathname === href.split("?")[0] ? "bg-blue-50 font-medium text-blue-700" : "text-slate-700 hover:bg-slate-50"}`}><Icon className="size-4" />{label}</Link>)}</nav></aside>;
  return <><button className="button-secondary fixed bottom-4 left-4 z-30 md:hidden" onClick={() => setOpen(true)}><Menu className="size-4" />メニュー</button><div className="hidden min-h-screen md:block">{menu}</div>{open && <div className="fixed inset-0 z-50 flex bg-slate-950/40 md:hidden">{menu}<button className="flex-1" aria-label="メニューを閉じる" onClick={() => setOpen(false)} /></div>}</>;
}
