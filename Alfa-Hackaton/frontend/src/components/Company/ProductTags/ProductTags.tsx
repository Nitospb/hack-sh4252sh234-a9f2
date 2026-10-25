import { PRODUCTS } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

const ProductTags = ({ products }: { products: Record<string, number> }) => (
  <div className={styles.prods}>
    {Object.entries(PRODUCTS).map(([key, label]) => (
      <em key={key} className={products[key] ? styles.y : ""}>
        {label}
      </em>
    ))}
  </div>
);

export default ProductTags;
