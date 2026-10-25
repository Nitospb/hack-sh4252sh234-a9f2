import Card from "@/src/components/UI/Card/Card";
import QuestionSuggestions from "../QuestionSuggestions/QuestionSuggestions";
import QuestionForm from "../QuestionForm/QuestionForm";

const AnalystCard = ({
  questions,
  eventId,
  title = "Спросить аналитика",
}: {
  questions: string[];
  eventId?: string;
  title?: string;
}) => (
  <Card title={title}>
    <QuestionSuggestions questions={questions} eventId={eventId} />
    <QuestionForm eventId={eventId} />
  </Card>
);

export default AnalystCard;
