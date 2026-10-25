import type { Metadata } from "next";
import { Suspense } from "react";
import Quality from "@/src/screens/Quality/Quality";

export const metadata: Metadata = { title: "Качество и метрики" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Quality />
    </Suspense>
  );
}
