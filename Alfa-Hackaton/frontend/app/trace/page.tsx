import type { Metadata } from "next";
import { Suspense } from "react";
import Trace from "@/src/screens/Trace/Trace";

export const metadata: Metadata = { title: "Журнал агента" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Trace />
    </Suspense>
  );
}
