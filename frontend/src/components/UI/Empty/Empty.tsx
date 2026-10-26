import type { ReactNode } from "react";
import Icon, { type IconName } from "@/src/components/UI/Icon/Icon";
import styles from "./Empty.module.css";

type EmptyProps = {
  title: string;
  description?: string;
  icon?: IconName;
  action?: ReactNode;
  className?: string;
  compact?: boolean;
};

export default function Empty({
  title,
  description,
  icon = "search",
  action,
  className = "",
  compact = false,
}: EmptyProps) {
  return (
    <div className={`${styles.empty} ${compact ? styles.compact : ""} ${className}`} role="status">
      <span className={styles.icon} aria-hidden="true"><Icon name={icon} size={28} /></span>
      <strong className={styles.title}>{title}</strong>
      {description && <p className={styles.description}>{description}</p>}
      {action && <div className={styles.action}>{action}</div>}
    </div>
  );
}
