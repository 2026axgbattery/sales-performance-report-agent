import type { ReactNode } from "react";

// README 배너(assets/readme/banner.svg)와 같은 시각 언어의 페이지 헤더 — 다크 카드 + 격자 패턴 + 좌측 오렌지 띠.
// 우측 액션(배치 선택·다운로드 등)은 밝은 배경 기준으로 만든 기존 컴포넌트를 그대로 쓰기 위해 흰 툴바 카드 위에 둔다.
export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    // overflow-hidden을 쓰지 않는다 — 액션 영역의 드롭다운(예: PDF 카테고리 선택)이 헤더 아래로 펼쳐질 때 잘리지 않도록.
    <div className="relative z-10 rounded-2xl bg-hero-grid px-7 py-6 text-white shadow-[var(--shadow-hero)]">
      <div className="absolute inset-y-0 left-0 w-1.5 rounded-l-2xl bg-[var(--sebang-orange)]" aria-hidden />
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-[22px] font-extrabold leading-tight tracking-tight">{title}</h1>
          {description && (
            <p className="mt-1.5 max-w-3xl text-sm leading-relaxed text-[var(--dark-gray-100)]">{description}</p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-2 rounded-xl bg-white p-2 text-[var(--color-text-primary)] shadow-[var(--shadow-card)]">
            {actions}
          </div>
        )}
      </div>
    </div>
  );
}
