import type { ReactNode } from "react";
import { Fragment } from "react";
import styles from "./KeyValueList.module.css";

const KeyValueList = ({ items }: { items: [string, ReactNode][] }) => (
  <dl className={styles.KeyValueList}>
    {items.map(([label, value]) => (
      <Fragment key={label}>
        <dt>{label}</dt>
        <dd>{value}</dd>
      </Fragment>
    ))}
  </dl>
);

export default KeyValueList;
