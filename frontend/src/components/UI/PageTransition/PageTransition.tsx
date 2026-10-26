import { ViewTransition, type ReactNode } from "react";

export default function PageTransition({ children }: { children: ReactNode }) {
  return <ViewTransition enter="page-fade-up-in" exit="page-fade-up-out" default="none">{children}</ViewTransition>;
}
