import styles from "@/src/styles/Design.module.css";

interface WeeklyChartProps {
  values: { label: string; value: number }[];
  color?: string;
  label: string;
}

const WeeklyChart = ({
  values,
  color = "var(--red)",
  label,
}: WeeklyChartProps) => (
  <div
    className={styles.chart}
    role="img"
    aria-label={`${label}: ${values.map((item) => `${item.label} — ${item.value}%`).join(", ")}`}
  >
    {values.map((item) => (
      <div key={item.label}>
        <b style={{ color: "var(--ink)" }}>{item.value}%</b>
        <i style={{ height: item.value * 1.5, background: color }} />
        {item.label}
      </div>
    ))}
  </div>
);

export default WeeklyChart;
