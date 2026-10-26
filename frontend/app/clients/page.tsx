import PageTransition from "@/src/components/UI/PageTransition/PageTransition";
import type { Metadata } from "next";
import Workspace from "@/src/screens/Workspace/Workspace";
export const metadata: Metadata = { title: "Выбор компании" };
export default function Page() { return <PageTransition><Workspace kind="clients" /></PageTransition>; }
