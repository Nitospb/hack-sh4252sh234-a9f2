import type { ReactNode } from "react";
import styles from "@/src/styles/Design.module.css";

export interface StepItem {
  title: ReactNode;
  detail: ReactNode;
  marker?: string;
  warning?: boolean;
}

const StepList = ({
  items,
  variant = "trace",
}: {
  items: StepItem[];
  variant?: "trace" | "process";
}) => (
  <ol
    className={`${styles.trace} ${variant === "process" ? styles.processSteps : ""}`}
  >
    {items.map((item, index) => (
      <li key={index}>
        <span className={`${styles.s} ${item.warning ? styles.w : ""}`}>
          {item.marker ?? index + 1}
        </span>
        <div>
          {item.title}
          <small>{item.detail}</small>
        </div>
      </li>
    ))}
  </ol>
);

export default StepList;
