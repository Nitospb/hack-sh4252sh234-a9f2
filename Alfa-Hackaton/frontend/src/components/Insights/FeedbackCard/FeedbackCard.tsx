"use client";

import { useState } from "react";
import { usePersistentState } from "@/src/hooks/usePersistentState";
import Card from "@/src/components/UI/Card/Card";
import Button from "@/src/components/UI/Button/Button";
import styles from "@/src/styles/Design.module.css";

const FeedbackCard = ({
  eventId,
  clientId,
}: {
  eventId: string;
  clientId: string;
}) => {
  const [feedback, setFeedback] = usePersistentState<string | null>(
    `alfa-feedback-${clientId}-${eventId}`,
    null,
  );
  const [choosingReason, setChoosingReason] = useState(false);

  return (
    <Card title="Полезен ли разбор?">
      {feedback ? (
        <p className={styles.muted} role="status">
          Спасибо! Учтём в персонализации.
        </p>
      ) : choosingReason ? (
        <div className={styles.stack}>
          <span>Что не так?</span>
          {["Нерелевантно", "Ошибка в фактах", "Слишком общо"].map((reason) => (
            <Button
              key={reason}
              variant="outline"
              onClick={() => setFeedback(reason)}
            >
              {reason}
            </Button>
          ))}
        </div>
      ) : (
        <div className={styles.fb}>
          <Button variant="outline" onClick={() => setFeedback("Полезно")}>
            👍 Да
          </Button>
          <Button variant="outline" onClick={() => setChoosingReason(true)}>
            👎 Нет
          </Button>
        </div>
      )}
    </Card>
  );
};

export default FeedbackCard;
