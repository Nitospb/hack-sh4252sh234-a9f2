"use client";

import { useState, type FormEvent } from "react";
import { usePersistentState } from "@/src/hooks/usePersistentState";
import Card from "@/src/components/UI/Card/Card";
import Button from "@/src/components/UI/Button/Button";
import styles from "@/src/styles/Design.module.css";

const ContextEditor = ({ clientId }: { clientId: string }) => {
  const [notes, setNotes] = usePersistentState<Record<string, string>>(
    `alfa-context-${clientId}`,
    {},
  );
  const [active, setActive] = useState<string | null>(null);
  const [value, setValue] = useState("");
  const handleSave = (event: FormEvent) => {
    event.preventDefault();
    if (active && value.trim())
      setNotes((previous) => ({ ...previous, [active]: value.trim() }));
    setActive(null);
  };

  return (
    <Card title="Уточнить данные">
      <div className={styles.stack} style={{ gap: 8 }}>
        {[
          "Добавить ключевых поставщиков",
          "Указать валюту экспортных контрактов",
          "Отметить, что есть хеджирование ставки",
        ].map((label) => (
          <div key={label}>
            <button
              className={styles.q}
              style={{ width: "100%" }}
              onClick={() => {
                setActive(label);
                setValue(notes[label] ?? "");
              }}
            >
              {label}
              {notes[label] && " ✓"}
            </button>
            {active === label && (
              <form
                onSubmit={handleSave}
                className={styles.stack}
                style={{ gap: 8, marginTop: 8 }}
              >
                <div className={styles.inp}>
                  <textarea
                    aria-label={label}
                    value={value}
                    onChange={(event) => setValue(event.target.value)}
                    required
                    autoFocus
                  />
                </div>
                <Button type="submit" variant="primary">
                  Сохранить
                </Button>
              </form>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
};

export default ContextEditor;
