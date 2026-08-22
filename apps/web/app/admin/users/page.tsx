"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, ShieldAlert, UserPlus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { ApiError, api } from "@/lib/api";

type Role = "owner" | "admin" | "member" | "viewer";
type MemberStatus = "invited" | "active" | "suspended" | "deleted";
type Organization = { id: string; name: string; role: Role };
type Permissions = { role: Role; permissions: string[] };
type OrgUser = { id: string; email: string; display_name: string; role: Role; status: MemberStatus; last_login_at: string | null; created_at: string; version: number };
type UserPage = { items: OrgUser[]; page: number; page_size: number; total: number };
type Invitation = { id: string; email: string; display_name: string; role: Role; expires_at: string; development_token?: string };

const inviteSchema = z.object({
  email: z.string().email("有効なメールアドレスを入力してください"),
  display_name: z.string().min(1, "表示名を入力してください").max(120),
  role: z.enum(["admin", "member", "viewer"]),
  message: z.string().max(1000),
  mode: z.enum(["invitation", "direct"]),
});
type InviteInput = z.infer<typeof inviteSchema>;

const labels: Record<Role | MemberStatus, string> = {
  owner: "所有者", admin: "管理者", member: "メンバー", viewer: "閲覧者",
  invited: "招待中", active: "有効", suspended: "停止中", deleted: "削除済み",
};

function csrfToken() {
  const value = document.cookie.split("; ").find((row) => row.startsWith("csrf_token="))?.split("=")[1];
  return value ? decodeURIComponent(value) : "";
}

export default function AdminUsersPage() {
  const client = useQueryClient();
  const [organizationId, setOrganizationId] = useState("");
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("");
  const [status, setStatus] = useState("");
  const [sort, setSort] = useState("-created_at");
  const [page, setPage] = useState(1);
  const [showInvite, setShowInvite] = useState(false);
  const [notice, setNotice] = useState("");

  const organizations = useQuery({ queryKey: ["organizations"], queryFn: () => api<Organization[]>("/organizations") });
  const activeOrg = organizationId || organizations.data?.[0]?.id || "";
  const permissions = useQuery({
    queryKey: ["user-permissions", activeOrg],
    queryFn: () => api<Permissions>(`/organizations/${activeOrg}/me/permissions`), enabled: !!activeOrg, retry: false,
  });
  const query = new URLSearchParams({ page: String(page), page_size: "20", sort, include_deleted: "true" });
  if (search) query.set("search", search);
  if (role) query.set("role", role);
  if (status) query.set("status", status);
  const users = useQuery({
    queryKey: ["admin-users", activeOrg, page, search, role, status, sort],
    queryFn: () => api<UserPage>(`/organizations/${activeOrg}/users?${query}`),
    enabled: !!activeOrg && !!permissions.data?.permissions.includes("organization.users.read"), retry: false,
  });
  const invitations = useQuery({
    queryKey: ["pending-invitations", activeOrg],
    queryFn: () => api<Invitation[]>(`/organizations/${activeOrg}/users/invitations/pending`),
    enabled: !!activeOrg && !!permissions.data?.permissions.includes("organization.users.read"),
  });
  const refresh = () => Promise.all([
    client.invalidateQueries({ queryKey: ["admin-users", activeOrg] }),
    client.invalidateQueries({ queryKey: ["pending-invitations", activeOrg] }),
  ]);
  const action = useMutation({
    mutationFn: ({ path, method = "POST", body }: { path: string; method?: string; body?: unknown }) =>
      api(path, { method, body: body ? JSON.stringify(body) : undefined, csrfToken: csrfToken() }),
    onSuccess: () => { setNotice("操作が完了しました。"); void refresh(); },
    onError: (error) => setNotice(error instanceof Error ? error.message : "操作に失敗しました。"),
  });
  const form = useForm<InviteInput>({ resolver: zodResolver(inviteSchema), defaultValues: { email: "", display_name: "", role: "member", message: "", mode: "invitation" } });
  const invite = useMutation({
    mutationFn: (body: InviteInput) => api<Invitation & { temporary_password?: string }>(`/organizations/${activeOrg}/users/${body.mode === "direct" ? "direct" : "invitations"}`, { method: "POST", body: JSON.stringify(body), csrfToken: csrfToken() }),
    onSuccess: (result) => { setShowInvite(false); form.reset(); setNotice(result.temporary_password ? `直接登録しました。開発用一時パスワード: ${result.temporary_password}` : result.development_token ? `招待を作成しました。開発用トークン: ${result.development_token}` : "メール送信キューへ登録しました。"); void refresh(); },
    onError: (error) => setNotice(error instanceof Error ? error.message : "招待に失敗しました。"),
  });

  if (permissions.isLoading || organizations.isLoading) return <main className="p-8">権限を確認しています…</main>;
  if (permissions.error instanceof ApiError && permissions.error.status === 403 || (permissions.data && !permissions.data.permissions.includes("organization.users.read"))) {
    return <main className="grid min-h-screen place-items-center p-8"><section className="card max-w-lg p-8 text-center"><ShieldAlert className="mx-auto mb-4 size-12 text-rose-600"/><h1 className="text-2xl font-semibold">403 — アクセスできません</h1><p className="mt-2 text-slate-600">このページを表示する権限がありません。</p><Link href="/" className="button-primary mt-6"><ArrowLeft className="size-4"/>プロジェクトへ戻る</Link></section></main>;
  }

  const can = (permission: string) => permissions.data?.permissions.includes(permission) ?? false;
  return <main className="min-h-screen bg-slate-50">
    <header className="border-b bg-white"><div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4"><div><Link href="/" className="text-sm text-blue-700">← プロジェクト</Link><h1 className="mt-1 text-2xl font-semibold">ユーザー管理</h1></div><div className="flex gap-2"><select className="field w-auto" value={activeOrg} onChange={(e) => { setOrganizationId(e.target.value); setPage(1); }}>{organizations.data?.map((org) => <option key={org.id} value={org.id}>{org.name}</option>)}</select><button className="button-primary" disabled={!can("organization.users.create")} onClick={() => setShowInvite(true)}><UserPlus className="size-4"/>ユーザーを招待</button></div></div></header>
    <div className="mx-auto max-w-7xl space-y-6 px-6 py-8">
      {notice && <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-900" role="status">{notice}</div>}
      <section className="card p-4"><div className="grid gap-3 md:grid-cols-5"><input className="field" placeholder="名前・メールで検索" value={search} onChange={(e) => { setSearch(e.target.value); setPage(1); }}/><select className="field" value={role} onChange={(e) => setRole(e.target.value)}><option value="">すべてのロール</option><option value="owner">所有者</option><option value="admin">管理者</option><option value="member">メンバー</option><option value="viewer">閲覧者</option></select><select className="field" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">すべての状態</option><option value="active">有効</option><option value="suspended">停止中</option><option value="deleted">削除済み</option></select><select className="field" value={sort} onChange={(e) => setSort(e.target.value)}><option value="-created_at">登録日の新しい順</option><option value="created_at">登録日の古い順</option><option value="display_name">表示名順</option><option value="email">メール順</option></select><button className="button-secondary" onClick={() => void refresh()}><RefreshCw className="size-4"/>更新</button></div></section>
      <section className="card overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-slate-50 text-slate-600"><tr><th className="p-4">表示名 / メール</th><th className="p-4">ロール</th><th className="p-4">状態</th><th className="p-4">最終ログイン</th><th className="p-4">登録日</th><th className="p-4">操作</th></tr></thead><tbody>{users.data?.items.map((target) => <tr key={target.id} className="border-t"><td className="p-4"><div className="font-medium">{target.display_name}</div><div className="text-slate-500">{target.email}</div></td><td className="p-4"><select className="field w-auto" value={target.role} disabled={!can("organization.users.change_role") || target.role === "owner"} onChange={(e) => { const next = e.target.value as Role; const warning = next === "admin" ? "管理権限が付与されます。追加される権限を確認し、続行しますか？" : `${labels[target.role]}から${labels[next]}へ変更しますか？`; if (confirm(warning)) { const reason = prompt("変更理由を入力してください"); if (reason) action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/role`, method: "PATCH", body: { role: next, version: target.version, reason } }); } }}><option value="owner">所有者</option><option value="admin">管理者</option><option value="member">メンバー</option><option value="viewer">閲覧者</option></select></td><td className="p-4"><span className="rounded-full bg-slate-100 px-2 py-1">{labels[target.status]}</span></td><td className="p-4">{target.last_login_at ? new Date(target.last_login_at).toLocaleString("ja-JP") : "—"}</td><td className="p-4">{new Date(target.created_at).toLocaleDateString("ja-JP")}</td><td className="p-4"><div className="flex flex-wrap gap-2">{target.status === "active" && <button className="text-amber-700" disabled={!can("organization.users.deactivate") || target.role === "owner"} onClick={() => { const reason = prompt("停止理由を入力してください"); if (reason) action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/suspend`, body: { reason, version: target.version } }); }}>停止</button>}{target.status === "suspended" && <button className="text-emerald-700" onClick={() => action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/activate`, body: { version: target.version, reason: "利用再開" } })}>再開</button>}{target.status !== "deleted" && <button className="text-rose-700" disabled={!can("organization.users.delete") || target.role === "owner"} onClick={() => { const typed = prompt(`削除するとログインできなくなります。過去のタスクとコメントは保持されます。確認のため「${target.display_name}」を入力してください。`); if (typed === target.display_name) { const reason = prompt("削除理由を入力してください"); if (reason) action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/delete`, body: { reason, version: target.version } }); } }}>削除</button>}{target.status === "deleted" && <button className="text-blue-700" disabled={!can("organization.users.restore")} onClick={() => action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/restore`, body: { version: target.version, reason: "管理画面から復元" } })}>復元</button>}<button className="text-blue-700" disabled={!can("organization.users.reset_password")} onClick={() => action.mutate({ path: `/organizations/${activeOrg}/users/${target.id}/request-password-reset` })}>PW再設定</button></div></td></tr>)}</tbody></table>{!users.isLoading && !users.data?.items.length && <p className="p-8 text-center text-slate-500">該当するユーザーはいません。</p>}<div className="flex items-center justify-between border-t p-4"><span>{users.data?.total ?? 0}件</span><div className="flex gap-2"><button className="button-secondary" disabled={page <= 1} onClick={() => setPage((v) => v - 1)}>前へ</button><span className="px-3 py-2">{page}</span><button className="button-secondary" disabled={page * 20 >= (users.data?.total ?? 0)} onClick={() => setPage((v) => v + 1)}>次へ</button></div></div></section>
      {!!invitations.data?.length && <section className="card p-5"><h2 className="text-lg font-semibold">招待中</h2><div className="mt-3 divide-y">{invitations.data.map((item) => <div key={item.id} className="flex items-center justify-between gap-4 py-3"><div><p className="font-medium">{item.display_name} <span className="text-sm text-slate-500">({item.email})</span></p><p className="text-xs text-slate-500">{labels[item.role]}・有効期限 {new Date(item.expires_at).toLocaleString("ja-JP")}</p></div><div className="flex gap-3"><button className="text-blue-700" onClick={() => action.mutate({ path: `/organizations/${activeOrg}/users/invitations/${item.id}/resend` })}>再送</button><button className="text-rose-700" onClick={() => action.mutate({ path: `/organizations/${activeOrg}/users/invitations/${item.id}/revoke` })}>取消</button></div></div>)}</div></section>}
    </div>
    {showInvite && <div className="fixed inset-0 grid place-items-center bg-slate-950/40 p-4"><form className="card w-full max-w-lg p-6" onSubmit={form.handleSubmit((value) => invite.mutate(value))}><h2 className="text-xl font-semibold">ユーザーを追加</h2><p className="mt-1 text-sm text-slate-600">招待方式では本人がパスワードを設定します。直接登録は組織設定で許可されている場合のみ利用できます。</p><div className="mt-5 space-y-4"><label><span className="label">登録方式</span><select className="field" {...form.register("mode")}><option value="invitation">招待（推奨）</option><option value="direct">直接登録（一時パスワード）</option></select></label><label><span className="label">メールアドレス</span><input className="field" {...form.register("email")}/><span className="text-sm text-rose-600">{form.formState.errors.email?.message}</span></label><label><span className="label">表示名</span><input className="field" {...form.register("display_name")}/></label><label><span className="label">初期ロール</span><select className="field" {...form.register("role")}><option value="member">メンバー</option><option value="viewer">閲覧者</option>{permissions.data?.role === "owner" && <option value="admin">管理者</option>}</select></label>{form.watch("role") === "admin" && <p className="rounded-lg bg-amber-50 p-3 text-sm text-amber-900">管理者はユーザーの編集・停止・削除・ロール変更を行えます。</p>}{form.watch("mode") === "invitation" && <label><span className="label">招待メッセージ（任意）</span><textarea className="field" rows={3} {...form.register("message")}/></label>}{form.watch("mode") === "direct" && <p className="rounded-lg bg-slate-100 p-3 text-sm text-slate-700">安全な一時パスワードを自動生成し、初回ログイン時に変更を強制します。</p>}</div><div className="mt-6 flex justify-end gap-2"><button type="button" className="button-secondary" onClick={() => setShowInvite(false)}>キャンセル</button><button className="button-primary" disabled={invite.isPending}>ユーザーを追加</button></div></form></div>}
  </main>;
}
