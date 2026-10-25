import Card from "@/src/components/UI/Card/Card";
import styles from "@/src/styles/Design.module.css";

const EmptyFeed = ({
  text = "Нет событий по выбранным фильтрам",
}: {
  text?: string;
}) => <Card className={styles.empty}>{text}</Card>;

export default EmptyFeed;
