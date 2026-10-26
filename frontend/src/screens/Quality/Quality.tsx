import PageHeader from "@/src/components/PageHeader/PageHeader";
import Card from "@/src/components/UI/Card/Card";
import Badge from "@/src/components/UI/Badge/Badge";
import StatCard from "@/src/components/UI/StatCard/StatCard";
import DataTable from "@/src/components/UI/DataTable/DataTable";
import StepList from "@/src/components/Agent/StepList/StepList";
import WeeklyChart from "@/src/components/Quality/WeeklyChart/WeeklyChart";
import {
  QUALITY_STATS,
  MODEL_ROWS,
  MONITORING_STEPS,
} from "@/src/data/quality";
import styles from "@/src/styles/Design.module.css";

const Quality = () => (
  <>
    <PageHeader
      title="Качество и метрики"
      description="Внутренний экран для команды банка: регулярный мониторинг контента, персонализации и AI-компонентов с учётом отзывов пользователей и экспертов."
      breadcrumbs={false}
    />
    <div className={`${styles.g4} ${styles.statGrid}`}>
      {QUALITY_STATS.map((stat) => (
        <StatCard key={stat.label} {...stat} />
      ))}
    </div>
    <div className={styles.grid}>
      <section className={styles.stack}>
        <Card
          heading={
            <>
              Оценки пользователей по неделям <Badge>👍 доля</Badge>
            </>
          }
        >
          <WeeklyChart
            label="Доля положительных оценок по неделям"
            values={[58, 61, 63, 66, 69, 71, 74].map((value, index) => ({
              label: `нед ${36 + index}`,
              value,
            }))}
          />
        </Card>
        <Card title="Очередь экспертной проверки">
          <DataTable
            headers={["Инсайт", "Клиент", "Сигнал", "Статус"]}
            rows={[
              [
                "Тенге ослаб на 4% к рублю",
                "U-22917",
                <Badge key="signal" tone="watch">
                  допущение 40%
                </Badge>,
                "На проверке",
              ],
              [
                "Ключевой контрагент сокращает поставки",
                "U-10482",
                <Badge key="signal" tone="watch">
                  сопоставление сущностей
                </Badge>,
                "На проверке",
              ],
              [
                "Субсидии на грузовой парк",
                "U-31055",
                <Badge key="signal" tone="risk">
                  👎 «нерелевантно»
                </Badge>,
                "Порог поднят",
              ],
              [
                "Ключевая ставка 14%",
                "U-10482",
                <Badge key="signal" tone="opp">
                  выборка 5%
                </Badge>,
                "Одобрено",
              ],
            ]}
          />
        </Card>
        <Card
          heading={
            <>
              Модели по задачам <Badge>только разрешённые LLM</Badge>
            </>
          }
        >
          <DataTable
            headers={["Задача", "Модель", "Вызовов/день", "Доля затрат"]}
            rows={MODEL_ROWS}
          />
        </Card>
      </section>
      <aside className={styles.sticky}>
        <Card title="Процесс мониторинга">
          <StepList items={MONITORING_STEPS} variant="process" />
        </Card>
      </aside>
    </div>
  </>
);

export default Quality;
