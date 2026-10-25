import type { ArchitectureNode } from "@/src/data/architecture";
import FlowNode from "../FlowNode/FlowNode";
import styles from "@/src/styles/Design.module.css";

const FlowLane = ({
  title,
  nodes,
}: {
  title: string;
  nodes: ArchitectureNode[];
}) => (
  <section className={styles.lane}>
    <h4>{title}</h4>
    {nodes.map((node) => (
      <FlowNode key={node.title} {...node} />
    ))}
  </section>
);

export default FlowLane;
