"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { chatHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

interface QuestionFormProps {
  eventId?: string;
  placeholder?: string;
  onSubmit?: (question: string) => void;
  disabled?: boolean;
}

const QuestionForm = ({
  eventId,
  placeholder = "Ваш вопрос…",
  onSubmit,
  disabled,
}: QuestionFormProps) => {
  const [question, setQuestion] = useState("");
  const router = useRouter();
  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    const text = question.trim();
    if (!text || disabled) return;
    if (onSubmit) onSubmit(text);
    else router.push(chatHref(text, eventId));
    setQuestion("");
  };

  return (
    <form className={styles.inp} onSubmit={handleSubmit}>
      <input
        aria-label={placeholder}
        placeholder={placeholder}
        value={question}
        onChange={(event) => setQuestion(event.target.value)}
        autoComplete="off"
        disabled={disabled}
      />
      <button
        type="submit"
        aria-label="Отправить вопрос"
        disabled={disabled || !question.trim()}
      >
        ↑
      </button>
    </form>
  );
};

export default QuestionForm;
