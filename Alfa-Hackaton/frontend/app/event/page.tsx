import type { Metadata } from "next";
import { Suspense } from "react";
import Event from "@/src/screens/Event/Event";

export const metadata: Metadata = { title: "Разбор события" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Event />
    </Suspense>
  );
}
