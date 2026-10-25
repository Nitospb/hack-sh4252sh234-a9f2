"use client";

import styles from "./Toggle.module.css";

interface ToggleProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
  label: string;
  color?: string;
}

const Toggle = ({
  checked,
  onChange,
  label,
  color = "var(--red)",
}: ToggleProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    className={`${styles.Toggle} ${checked ? styles.on : ""}`}
    style={{ background: checked ? color : undefined }}
    onClick={() => onChange(!checked)}
  />
);

export default Toggle;
