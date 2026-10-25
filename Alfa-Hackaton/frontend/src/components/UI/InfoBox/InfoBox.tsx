import type { ReactNode } from "react";
import styles from "@/src/styles/Design.module.css";

interface InfoBoxProps {
  title: ReactNode;
  tone?: "bank" | "ai" | "fct";
  children: ReactNode;
  background?: string;
  borderColor?: string;
}

const InfoBox = ({
  title,
  tone = "ai",
  children,
  background,
  borderColor,
}: InfoBoxProps) => (
  <div
    className={`${styles.box} ${styles[tone]}`}
    style={{ background, borderColor }}
  >
    <h4>{title}</h4>
    {children}
  </div>
);

export default InfoBox;
