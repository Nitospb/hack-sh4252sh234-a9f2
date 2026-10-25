import type { Metadata } from "next";
import { Suspense } from "react";
import Architecture from "@/src/screens/Architecture/Architecture";

export const metadata: Metadata = { title: "Архитектура решения" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Architecture />
    </Suspense>
  );
}
