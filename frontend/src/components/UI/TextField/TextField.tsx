"use client";

import type { InputHTMLAttributes, ReactNode } from "react";
import styles from "./TextField.module.css";

interface TextFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "onChange" | "size"> {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
  error?: string;
  leadingIcon?: ReactNode;
}

export default function TextField({
  id,
  label,
  value,
  onChange,
  hint,
  error,
  leadingIcon,
  className = "",
  disabled,
  ...inputProps
}: TextFieldProps) {
  const description = error || hint;

  return (
    <div className={`${styles.field} ${error ? styles.invalid : ""} ${disabled ? styles.disabled : ""} ${className}`}>
      <div className={styles.frame}>
        <label htmlFor={id} className={styles.label}>{label}</label>
        <div className={styles.control}>
          {leadingIcon && <span className={styles.icon} aria-hidden="true">{leadingIcon}</span>}
          <input
            {...inputProps}
            id={id}
            value={value}
            disabled={disabled}
            aria-invalid={Boolean(error)}
            aria-describedby={description ? `${id}-description` : undefined}
            onChange={(event) => onChange(event.target.value)}
          />
        </div>
      </div>
      {description && <p id={`${id}-description`} className={error ? styles.error : styles.hint}>{description}</p>}
    </div>
  );
}
