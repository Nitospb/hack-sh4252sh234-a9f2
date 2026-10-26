import Empty from "@/src/components/UI/Empty/Empty";

const EmptyFeed = ({
  text = "Нет событий по выбранным фильтрам",
}: {
  text?: string;
}) => <Empty title="Пока нет событий" description={text} icon="news" />;

export default EmptyFeed;
