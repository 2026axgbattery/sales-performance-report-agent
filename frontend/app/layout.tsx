import type { Metadata } from "next";

import { TopNav } from "@/components/TopNav";

import "./globals.css";

export const metadata: Metadata = {
  title: "영업실적·손익 분석 Agent",
  description: "SAP 실적 업로드로 팀·제품군별 손익을 집계·이상징후 탐지하는 Agent (MVP)",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko" className="h-full">
      <body className="flex min-h-full flex-col bg-[var(--color-bg-page)]">
        <TopNav />
        <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-6">{children}</main>
      </body>
    </html>
  );
}
