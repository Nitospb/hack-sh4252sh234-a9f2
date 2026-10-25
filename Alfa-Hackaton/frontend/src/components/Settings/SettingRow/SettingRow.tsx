import type { ReactNode } from "react";
import styles from "@/src/styles/Design.module.css";

const SettingRow = ({
  label,
  description,
  control,
  children,
}: {
  label: string;
  description: string;
  control?: ReactNode;
  children?: ReactNode;
}) => (
  <div className={styles.opt}>
    <div>
      {label}
      <small>{description}</small>
      {children}
    </div>
    {control}
  </div>
);

export default SettingRow;
