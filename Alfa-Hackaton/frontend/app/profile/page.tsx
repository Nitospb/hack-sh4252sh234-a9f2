import type { Metadata } from "next";
import { Suspense } from "react";
import Profile from "@/src/screens/Profile/Profile";

export const metadata: Metadata = { title: "Контекст компании" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Profile />
    </Suspense>
  );
}
