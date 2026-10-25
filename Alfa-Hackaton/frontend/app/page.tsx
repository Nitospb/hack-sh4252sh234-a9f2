import type { Metadata } from "next";
import { Suspense } from "react";
import Home from "@/src/screens/Home/Home";

export const metadata: Metadata = { title: "Главная" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Home />
    </Suspense>
  );
}
