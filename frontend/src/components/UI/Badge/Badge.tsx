import type { CSSProperties, ReactNode } from "react";
import styles from "./Badge.module.css";

export type BadgeTone =
  "risk" | "opp" | "watch" | "bank" | "ai" | "fact" | "gray" | "dark";

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  color?: string;
  background?: string;
  borderColor?: string;
  className?: string;
  style?: CSSProperties;
}

const Badge = ({
  children,
  tone = "gray",
  color,
  background,
  borderColor,
  className = "",
  style,
}: BadgeProps) => (
  <span
    className={`${styles.Badge} ${styles[tone]} ${className}`}
    style={{ color, background, borderColor, ...style }}
  >
    {children}
  </span>
);

export default Badge;
