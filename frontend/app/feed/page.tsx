import PageTransition from "@/src/components/UI/PageTransition/PageTransition";
import type { Metadata } from "next";
import { Suspense } from "react";
import Feed from "@/src/screens/Feed/Feed";
import Skeleton from "@/src/components/UI/Skeleton/Skeleton";

export const metadata: Metadata = { title: "Лента инсайтов" };

export default function Page() {
  return (
    <PageTransition><Suspense fallback={<Skeleton variant="cards" count={3} label="Загрузка новостной ленты"/>}>
      <Feed />
    </Suspense></PageTransition>
  );
}
