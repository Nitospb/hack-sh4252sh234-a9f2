import Link from "next/link";
import { chatHref } from "@/src/utils/insights";
import styles from "@/src/styles/Design.module.css";

const QuestionSuggestions = ({
  questions,
  eventId,
}: {
  questions: string[];
  eventId?: string;
}) => (
  <div className={styles.stack} style={{ gap: 8 }}>
    {questions.map((question) => (
      <Link
        className={styles.q}
        key={question}
        href={chatHref(question, eventId)}
      >
        {question}
      </Link>
    ))}
  </div>
);

export default QuestionSuggestions;
