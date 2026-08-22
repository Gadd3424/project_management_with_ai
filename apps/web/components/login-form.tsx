"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { LoaderCircle } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { api } from "@/lib/api";

const schema = z.object({ email: z.email(), password: z.string().min(8) });
type Values = z.infer<typeof schema>;

export function LoginForm({ onLogin }: { onLogin: (csrf: string) => void }) {
  const [passwordChange, setPasswordChange] = useState<{ current: string; csrf: string } | null>(null);
  const [newPassword, setNewPassword] = useState("");
  const [changeError, setChangeError] = useState("");
  const { register, handleSubmit, formState: { errors, isSubmitting }, setError } = useForm<Values>({
    resolver: zodResolver(schema), defaultValues: { email: "demo@example.com", password: "DemoPass123!" },
  });
  const submit = async (values: Values) => {
    try {
      const result = await api<{ csrf_token: string; user: { force_password_change: boolean } }>("/auth/login", { method: "POST", body: JSON.stringify(values) });
      if (result.user.force_password_change) {
        setPasswordChange({ current: values.password, csrf: result.csrf_token });
        return;
      }
      onLogin(result.csrf_token);
    } catch (error) {
      setError("root", { message: error instanceof Error ? error.message : "ログインできませんでした" });
    }
  };
  if (passwordChange) return (
    <main className="grid min-h-screen place-items-center p-6"><form className="card w-full max-w-md space-y-5 p-8" onSubmit={async (event) => { event.preventDefault(); setChangeError(""); try { await api("/auth/change-password", { method: "POST", csrfToken: passwordChange.csrf, body: JSON.stringify({ current_password: passwordChange.current, new_password: newPassword }) }); setPasswordChange(null); setNewPassword(""); setError("root", { message: "パスワードを変更しました。新しいパスワードでログインしてください。" }); } catch (error) { setChangeError(error instanceof Error ? error.message : "変更できませんでした"); } }}><div><p className="text-sm font-medium text-amber-700">初回ログイン</p><h1 className="mt-1 text-2xl font-semibold">パスワードを変更</h1><p className="mt-2 text-sm text-slate-600">一時パスワードは継続利用できません。</p></div><label><span className="label">新しいパスワード（12文字以上）</span><input className="field" type="password" minLength={12} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)}/></label>{changeError && <p className="text-sm text-red-600">{changeError}</p>}<button className="button-primary w-full">パスワードを変更</button></form></main>
  );
  return (
    <main className="grid min-h-screen place-items-center p-6">
      <form onSubmit={handleSubmit(submit)} className="card w-full max-w-md space-y-5 p-8">
        <div><p className="text-sm font-medium text-blue-600">PROJECT INTELLIGENCE</p><h1 className="mt-1 text-2xl font-semibold">ログイン</h1></div>
        <div><label className="label" htmlFor="email">メール</label><input id="email" className="field" {...register("email")} />{errors.email && <p className="mt-1 text-sm text-red-600">{errors.email.message}</p>}</div>
        <div><label className="label" htmlFor="password">パスワード</label><input id="password" type="password" className="field" {...register("password")} />{errors.password && <p className="mt-1 text-sm text-red-600">{errors.password.message}</p>}</div>
        {errors.root && <p role="alert" className="text-sm text-red-600">{errors.root.message}</p>}
        <button className="button-primary w-full" disabled={isSubmitting}>{isSubmitting && <LoaderCircle className="size-4 animate-spin" />}ログイン</button>
        <p className="text-xs text-slate-500">デモ認証情報は入力済みです。</p>
      </form>
    </main>
  );
}
