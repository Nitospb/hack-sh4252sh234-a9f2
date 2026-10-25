import type { Metadata } from "next";
import { Suspense } from "react";
import Feed from "@/src/screens/Feed/Feed";

export const metadata: Metadata = { title: "Лента инсайтов" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Feed />
    </Suspense>
  );
}
