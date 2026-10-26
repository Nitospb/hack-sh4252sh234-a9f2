import type { Metadata } from "next";
import Workspace from "@/src/screens/Workspace/Workspace";
export const metadata: Metadata = { title: "Архитектура" };
export default function Page() { return <Workspace kind="architecture" />; }
