"use client";

import { useEffect, useState, type ReactNode } from "react";
import s from "./Skeleton.module.css";

type Props = { loading: boolean; placeholder: ReactNode; children: ReactNode; className?: string };

export default function LoadingSwap({ loading, placeholder, children, className = "" }: Props) {
  const [visible, setVisible] = useState(loading);
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    if (loading) {
      const timer = setTimeout(() => { setVisible(true); setLeaving(false); }, 0);
      return () => clearTimeout(timer);
    }
    if (!visible) return;
    const start = setTimeout(() => setLeaving(true), 0);
    const duration = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300;
    const finish = setTimeout(() => { setVisible(false); setLeaving(false); }, duration);
    return () => { clearTimeout(start); clearTimeout(finish); };
  }, [loading, visible]);

  return <div className={`${className} ${s.swap} ${visible ? leaving ? s.leaving : s.placeholder : s.enter}`.trim()} aria-busy={loading}>
    {visible ? placeholder : children}
  </div>;
}
