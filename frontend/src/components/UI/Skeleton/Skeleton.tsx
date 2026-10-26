import s from "./Skeleton.module.css";

type Props = { variant?: "lines" | "cards" | "facts"; count?: number; label?: string };

export default function Skeleton({ variant = "lines", count = 3, label = "Загрузка данных" }: Props) {
  return <div className={s[variant]} role="status" aria-label={label}>
    {Array.from({ length: count }, (_, index) => <div className={s.item} aria-hidden="true" key={index}>
      <i className={s.short} /><i className={s.long} /><i className={s.medium} />
    </div>)}
  </div>;
}

export function PageSkeleton() { return <Skeleton variant="cards" count={3} label="Загрузка страницы" />; }
export function ContextSkeleton() { return <Skeleton variant="facts" count={3} label="Загрузка ваших интересов" />; }
