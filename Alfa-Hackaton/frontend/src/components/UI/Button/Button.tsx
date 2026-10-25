import Link from "next/link";
import type { ButtonHTMLAttributes, CSSProperties, ReactNode } from "react";
import styles from "./Button.module.css";

interface SharedProps {
  children: ReactNode;
  variant?: "default" | "primary" | "dark" | "outline";
  background?: string;
  color?: string;
  borderColor?: string;
  className?: string;
  style?: CSSProperties;
}

type ButtonProps = SharedProps &
  (
    | ({ href: string; onClick?: () => void } & Omit<
        ButtonHTMLAttributes<HTMLButtonElement>,
        "onClick"
      >)
    | ({ href?: never } & ButtonHTMLAttributes<HTMLButtonElement>)
  );

const Button = ({
  children,
  variant = "default",
  background,
  color,
  borderColor,
  className = "",
  style,
  href,
  ...props
}: ButtonProps) => {
  const shared = {
    className: `${styles.Button} ${styles[variant]} ${className}`,
    style: { background, color, borderColor, ...style },
  };
  if (href)
    return (
      <Link href={href} {...shared} onClick={props.onClick as () => void}>
        {children}
      </Link>
    );
  return (
    <button type="button" {...props} {...shared}>
      {children}
    </button>
  );
};

export default Button;
