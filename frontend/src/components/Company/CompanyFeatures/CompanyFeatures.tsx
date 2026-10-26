import Badge from "@/src/components/UI/Badge/Badge";
import Card from "@/src/components/UI/Card/Card";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import type { Client } from "@/src/types";
import styles from "@/src/styles/Design.module.css";

const CompanyFeatures = ({ client: c }: { client: Client }) => {
  const yesNo = (value: number) => (value ? "Да" : "Нет");
  const features: [string, string, string, number][] = [
    ["SYNTHETIC_U", "Идентификатор", c.id, 0],
    ["ORG_TYPE", "Тип организации", c.orgType, 10],
    ["OKFS_NAME", "Форма собственности", c.okfs, 5],
    [
      "MAINOKVED_CODE / NAME",
      "Основной вид деятельности",
      `${c.okved} · ${c.okvedName}`,
      95,
    ],
    ["REVENUE_COMPANY", "Годовая выручка", c.revenue, 70],
    ["COMPANY_AGE_YEARS_GRADATION", "Возраст", c.age, 20],
    ["ECO_MARK_LABEL", "Стадия развития", c.stage, 35],
    ["AMOUNT_WORKERS_FNS_GRADATION", "Сотрудники (ФНС)", c.workers, 30],
    ["CL_PRODUCT_LOA_MARK", "Кредитные продукты", yesNo(c.products.LOA), 85],
    ["CL_PRODUCT_LEA_MARK", "Лизинг", yesNo(c.products.LEA), 60],
    ["CL_PRODUCT_DEP_MARK", "Депозиты", yesNo(c.products.DEP), 55],
    ["CL_PRODUCT_GAR_MARK", "Гарантии", yesNo(c.products.GAR), 40],
    ["FACTORING_MARK", "Факторинг", yesNo(c.products.FACT), 40],
    ["CL_PRODUCT_ZPP_MARK", "Зарплатный проект", yesNo(c.products.ZPP), 15],
    ["FTS_COUNTRY_NAME", "Страна (ФТС)", c.fts, c.fts === "Россия" ? 10 : 80],
    ["REGION / CITY", "Регион регистрации", `${c.region}, ${c.city}`, 45],
    ["GROUP_ID", "Группа компаний", c.group, 50],
    ["CL_TYPE", "Тип клиента", c.clType, 0],
  ];

  return (
    <Card
      heading={
        <>
          Признаки из данных банка <Badge>df_Uid_data_hack.csv</Badge>
        </>
      }
      action={<span className={styles.link}>Вес в отборе</span>}
    >
      <DataTable
        headers={["Поле", "Признак", "Значение", "Вес"]}
        rows={features.map(([field, name, value, weight]) => [
          <span className={`${styles.mono} ${styles.muted}`} key={field}>
            {field}
          </span>,
          name,
          <b key={field}>{value}</b>,
          weight ? (
            <span
              key={field}
              className={styles.weight}
              style={{ width: weight, opacity: 0.35 + weight / 150 }}
              aria-label={`Вес ${weight}%`}
            />
          ) : (
            <span key={field} className={`${styles.muted} ${styles.small}`}>
              не влияет
            </span>
          ),
        ])}
      />
    </Card>
  );
};

export default CompanyFeatures;
