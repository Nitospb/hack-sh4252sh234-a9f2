import Link from "next/link";
import { DOCS } from "@/src/data/demo";
import FeatureTags from "@/src/components/Company/FeatureTags/FeatureTags";
import styles from "@/src/styles/Design.module.css";

const SourceList = ({
  ids,
  features,
}: {
  ids: string[];
  features?: string[];
}) => (
  <div className={styles.srcl}>
    {ids.map((id, index) => (
      <Link href={`/sources#${id}`} key={id}>
        <b>
          [{index + 1}] {DOCS[id].t}
        </b>
        <small>
          {DOCS[id].k} · {DOCS[id].date} · {DOCS[id].type}
        </small>
      </Link>
    ))}
    {features && (
      <Link href="/profile">
        <b>Признаки клиента</b>
        <FeatureTags features={features} />
      </Link>
    )}
  </div>
);

export default SourceList;
