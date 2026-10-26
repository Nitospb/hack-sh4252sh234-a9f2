"use client";

import styles from "./FilterPills.module.css";

interface FilterPillsProps {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  label: string;
  action?: { label: string; onClick: () => void };
  nowrap?: boolean;
}

const FilterPills = ({ options, value, onChange, label, action, nowrap = false }: FilterPillsProps) => (
  <div className={`${styles.FilterPills} ${nowrap ? styles.nowrap : ""}`} role="group" aria-label={label}>
    {options.map((option) => (
      <button
        type="button"
        key={option.value}
        aria-pressed={option.value === value}
        className={`${styles.pill} ${option.value === value ? styles.on : ""}`}
        onClick={() => onChange(option.value)}
      >
        {option.label}
      </button>
    ))}
    {action && <button type="button" className={styles.pill} onClick={action.onClick}>{action.label}</button>}
  </div>
);

export default FilterPills;
