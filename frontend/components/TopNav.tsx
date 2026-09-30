"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/upload", label: "F1 업로드" },
  { href: "/overview", label: "F4 Overview" },
  { href: "/anomalies", label: "F5 이상징후 하이라이트" },
  { href: "/thresholds", label: "F6 임계치 설정" },
  { href: "/reports", label: "F7 보고서 초안" },
];

export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="relative bg-hero-grid text-white">
      <div className="absolute inset-y-0 left-0 w-1.5 bg-[var(--sebang-orange)]" aria-hidden />
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-3.5">
        <div className="flex items-center gap-3">
          <Image
            src="/rocket-emblem.png"
            alt="ROCKET"
            width={40}
            height={40}
            priority
            className="h-10 w-10 rounded-full"
          />
          <div>
            <div className="text-[17px] font-bold leading-tight">
              영업실적·손익 분석 <span className="text-[var(--sebang-orange)]">Agent</span>
            </div>
            <div className="text-[12px] text-[var(--dark-gray-100)]">국내영업기획팀 · 김영우 책임</div>
          </div>
        </div>
        <nav className="flex items-center gap-1">
          {NAV_ITEMS.map((item) => {
            const active = pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`relative rounded-md px-3 py-2 text-sm font-semibold transition-colors ${
                  active
                    ? "bg-white/10 text-white"
                    : "text-[var(--dark-gray-100)] hover:bg-white/5 hover:text-white"
                }`}
              >
                {item.label}
                {active && (
                  <span className="absolute inset-x-3 -bottom-[5px] h-[3px] rounded-full bg-[var(--sebang-orange)]" />
                )}
              </Link>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
