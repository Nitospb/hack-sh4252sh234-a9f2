"use client";

import { useEffect, useState } from "react";
import Image from "next/image";
import styles from "./SitePreloader.module.css";

export default function SitePreloader() {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    // Also clear the overlay if its CSS animation finished before hydration.
    const timeout = window.setTimeout(() => setVisible(false), 1900);
    return () => window.clearTimeout(timeout);
  }, []);

  if (!visible) return null;

  return (
    <div
      className={styles.overlay}
      role="status"
      aria-label="Загрузка Альфа-Бизнес"
      onAnimationEnd={(event) => {
        if (event.target === event.currentTarget) setVisible(false);
      }}
    >
      <Image
        className={styles.mark}
        src="/alfa-bank-mark-red.svg"
        alt=""
        width={80}
        height={100}
        priority
        unoptimized
      />
    </div>
  );
}
