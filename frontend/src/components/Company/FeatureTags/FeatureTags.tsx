import styles from "@/src/styles/Design.module.css";

const FeatureTags = ({ features }: { features: string[] }) => (
  <div className={styles.prods}>
    {features.map((feature) => (
      <em key={feature} className={`${styles.y} ${styles.mono}`}>
        {feature}
      </em>
    ))}
  </div>
);

export default FeatureTags;
