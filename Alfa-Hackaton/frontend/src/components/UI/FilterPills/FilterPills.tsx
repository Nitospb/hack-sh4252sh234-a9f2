"use client";

import styles from "./FilterPills.module.css";

interface FilterPillsProps {
  options: { value: string; label: string }[];
  value: string;
  onChange: (value: string) => void;
  label: string;
}

const FilterPills = ({ options, value, onChange, label }: FilterPillsProps) => (
  <div className={styles.FilterPills} role="group" aria-label={label}>
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
  </div>
);

export default FilterPills;
