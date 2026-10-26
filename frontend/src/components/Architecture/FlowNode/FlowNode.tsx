import type { ArchitectureNode } from "@/src/data/architecture";
import styles from "@/src/styles/Design.module.css";

const FlowNode = ({ title, description, tone }: ArchitectureNode) => (
  <div
    className={`${styles.nd} ${tone === "bank" ? styles.bk : ""} ${tone === "agent" ? styles.ag : ""}`}
  >
    {title}
    <small>{description}</small>
  </div>
);

export default FlowNode;
