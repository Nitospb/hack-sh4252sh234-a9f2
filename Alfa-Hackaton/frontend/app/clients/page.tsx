import type { Metadata } from "next";
import { Suspense } from "react";
import Clients from "@/src/screens/Clients/Clients";

export const metadata: Metadata = { title: "Выбор клиента" };

export default function Page() {
  return (
    <Suspense fallback={<p>Загрузка…</p>}>
      <Clients />
    </Suspense>
  );
}
