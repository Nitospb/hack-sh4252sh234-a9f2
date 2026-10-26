import type { CSSProperties } from "react";
import styles from "./Avatar.module.css";

interface AvatarProps {
  text: string;
  size?: number;
  background?: string;
  color?: string;
  radius?: CSSProperties["borderRadius"];
}

const Avatar = ({
  text,
  size = 32,
  background = "var(--ink)",
  color = "#fff",
  radius = "50%",
}: AvatarProps) => (
  <div
    className={styles.Avatar}
    style={{
      width: size,
      height: size,
      background,
      color,
      borderRadius: radius,
    }}
  >
    {text}
  </div>
);

export default Avatar;
