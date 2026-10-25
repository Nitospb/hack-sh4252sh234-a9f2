import type { Metadata } from "next";
import { Suspense } from "react";
import Settings from "@/src/screens/Settings/Settings";

export const metadata: Metadata = { title: "Настройки ленты" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Settings />
    </Suspense>
  );
}
