import type { Metadata } from "next";
import Workspace from "@/src/screens/Workspace/Workspace";
export const metadata: Metadata = { title: "Источники" };
export default function Page() { return <Workspace kind="sources" />; }
