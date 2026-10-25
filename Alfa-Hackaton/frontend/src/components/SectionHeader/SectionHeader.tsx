import type { ReactNode } from "react";
import styles from "@/src/styles/Design.module.css";

interface SectionHeaderProps {
  title: string;
  action?: ReactNode;
  description?: string;
  spaced?: boolean;
}

const SectionHeader = ({
  title,
  action,
  description,
  spaced,
}: SectionHeaderProps) => (
  <div className={`${styles["sec-h"]} ${spaced ? styles.sectionGap : ""}`}>
    <h2>{title}</h2>
    {description && (
      <span className={`${styles.muted} ${styles.small}`}>{description}</span>
    )}
    {action}
  </div>
);

export default SectionHeader;
