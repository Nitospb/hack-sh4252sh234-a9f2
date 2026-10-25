import type { Metadata } from "next";
import { Suspense } from "react";
import Sources from "@/src/screens/Sources/Sources";

export const metadata: Metadata = { title: "Источники" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Sources />
    </Suspense>
  );
}
