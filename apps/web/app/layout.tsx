import type { Metadata } from "next";
import "./globals.css";
import { Providers } from "./providers";

export const metadata: Metadata = {
  title: "Evolutionary Project AI",
  description: "説明可能なAI提案付きプロジェクト管理",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ja">
      <body><Providers>{children}</Providers></body>
    </html>
  );
}

