import PageTransition from "@/src/components/UI/PageTransition/PageTransition";
import type { Metadata } from "next";
import Kit from "@/src/screens/Kit/Kit";

export const metadata: Metadata = { title: "Библиотека компонентов" };

export default function Page() {
  return <PageTransition><Kit /></PageTransition>;
}
