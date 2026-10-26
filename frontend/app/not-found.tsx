import Button from "@/src/components/UI/Button/Button";
import Card from "@/src/components/UI/Card/Card";

export default function NotFound() {
  return (
    <Card title="Страница не найдена">
      <p>Проверьте адрес или вернитесь на главную.</p>
      <Button href="/" variant="primary">
        На главную
      </Button>
    </Card>
  );
}
