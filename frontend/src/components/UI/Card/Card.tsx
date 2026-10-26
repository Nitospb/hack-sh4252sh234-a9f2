import type { CSSProperties, HTMLAttributes, ReactNode } from "react";
import styles from "./Card.module.css";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  heading?: ReactNode;
  action?: ReactNode;
  background?: string;
  borderColor?: string;
  padding?: CSSProperties["padding"];
}

const Card = ({
  title,
  heading,
  action,
  background,
  borderColor,
  padding,
  className = "",
  style,
  children,
  ...props
}: CardProps) => (
  <div
    className={`${styles.Card} ${className}`}
    style={{
      background,
      borderColor,
      borderWidth: borderColor ? 2 : undefined,
      padding,
      ...style,
    }}
    {...props}
  >
    {(title || heading) && (
      <h3 className={styles.heading}>
        {title || heading}
        {action && <span className={styles.action}>{action}</span>}
      </h3>
    )}
    {children}
  </div>
);

export default Card;
