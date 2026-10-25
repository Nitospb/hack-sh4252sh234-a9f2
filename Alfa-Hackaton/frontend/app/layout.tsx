import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Suspense } from "react";
import ClientProvider from "@/src/providers/ClientProvider";
import AppShell from "@/src/components/AppShell/AppShell";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "Альфа-Бизнес · Главная",
    template: "%s · Альфа-Бизнес",
  },
  description:
    "Персональная новостная аналитика для вашего бизнеса: события, риски, возможности и позиция Альфа-Банка.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="ru">
      <body>
        <Suspense fallback={<p>Загрузка…</p>}>
          <ClientProvider>
            <AppShell>{children}</AppShell>
          </ClientProvider>
        </Suspense>
      </body>
    </html>
  );
}
