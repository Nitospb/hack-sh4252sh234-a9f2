import type { ReactNode } from "react";
import Card from "../Card/Card";
import styles from "./StatCard.module.css";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  trend?: "positive" | "negative";
  compact?: boolean;
}

const StatCard = ({ label, value, detail, trend, compact }: StatCardProps) => (
  <Card className={`${styles.StatCard} ${compact ? styles.compact : ""}`}>
    <small>{label}</small>
    <b>{value}</b>
    {detail && <small className={trend ? styles[trend] : ""}>{detail}</small>}
  </Card>
);

export default StatCard;
