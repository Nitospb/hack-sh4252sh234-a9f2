import type { Metadata } from "next";
import Workspace from "@/src/screens/Workspace/Workspace";
export const metadata: Metadata = { title: "Настройки ленты" };
export default function Page() { return <Workspace kind="settings" />; }
