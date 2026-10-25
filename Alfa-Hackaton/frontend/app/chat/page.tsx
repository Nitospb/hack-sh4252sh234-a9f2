import type { Metadata } from "next";
import { Suspense } from "react";
import Chat from "@/src/screens/Chat/Chat";

export const metadata: Metadata = { title: "Спросить аналитика" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Chat />
    </Suspense>
  );
}
