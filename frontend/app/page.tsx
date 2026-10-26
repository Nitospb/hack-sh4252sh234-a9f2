import PageTransition from "@/src/components/UI/PageTransition/PageTransition";
import type { Metadata } from "next";
import HomeDashboard from "@/src/screens/Home/HomeDashboard";
export const metadata: Metadata = { title: "Главная" };
export default function Page() { return <PageTransition><HomeDashboard /></PageTransition>; }
