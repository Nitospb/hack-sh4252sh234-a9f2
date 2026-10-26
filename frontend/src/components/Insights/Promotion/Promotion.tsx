"use client";

import { useClient } from "@/src/providers/ClientProvider";
import type { Interpretation } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const Promotion = ({ promotion }: { promotion?: Interpretation["promo"] }) => {
  const { settings } = useClient();
  if (!promotion || !settings.promotions) return null;
  return (
    <div className={styles.promo}>
      <b>{promotion.t}:</b> {promotion.d}
      <small>Предложение банка · реклама</small>
    </div>
  );
};

export default Promotion;
