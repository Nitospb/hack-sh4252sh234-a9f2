"""OpenAPI contract for the public Next BFF surface of the local service."""

from copy import deepcopy


def parameter(name, description, *, required=False, kind="string", **schema):
    return {
        "name": name,
        "in": "query",
        "required": required,
        "description": description,
        "schema": {"type": kind, **schema},
    }


COMPANY = parameter("company_id", "Идентификатор компании.", required=True)
RECORD = parameter("source_record_id", "Идентификатор строки исходного профиля; выбирает конкретную запись компании.")
USER = parameter("user_id", "Локальный идентификатор пользователя прототипа.", default="local")
SCOPE = [COMPANY, RECORD, USER]
JSON_RESPONSE = {"description": "JSON-ответ сервиса.", "content": {"application/json": {"schema": {"type": "object"}}}}
ERROR_RESPONSE = {"description": "Ошибка запроса.", "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}}}


def model_response(name, description):
    return {"description": description, "content": {"application/json": {"schema": {"$ref": f"#/components/schemas/{name}"}}}}


def get(summary, parameters=(), *, tag="Данные", response=None):
    return {
        "tags": [tag],
        "summary": summary,
        "parameters": deepcopy(list(parameters)),
        "responses": {"200": deepcopy(response or JSON_RESPONSE), "400": deepcopy(ERROR_RESPONSE), "403": deepcopy(ERROR_RESPONSE)},
    }


def post(summary, required=(), optional=(), *, tag="Состояние", status="200", description=None):
    properties = {
        "company_id": {"type": "string", "minLength": 1, "maxLength": 200, "description": "Идентификатор компании."},
        "source_record_id": {"type": "string", "description": "Идентификатор строки профиля."},
        "user_id": {"type": "string", "default": "local", "description": "Локальный пользователь прототипа."},
        **deepcopy(optional),
    }
    return {
        "tags": [tag],
        "summary": summary,
        **({"description": description} if description else {}),
        "requestBody": {
            "required": True,
            "content": {"application/json": {"schema": {
                "type": "object", "required": ["company_id", *required],
                "properties": properties, "additionalProperties": False,
            }}},
        },
        "responses": {status: model_response("JobAccepted", "Запуск принят в очередь.") if status == "202" else deepcopy(JSON_RESPONSE), "400": deepcopy(ERROR_RESPONSE), "403": deepcopy(ERROR_RESPONSE), "503": deepcopy(ERROR_RESPONSE)},
    }


def field(description, *, kind="string", **schema):
    return {"type": kind, "description": description, **schema}


def specification():
    article = {"article_id": field("Канонический Article ID.", minLength=1)}
    role = {"role": field("Роль пользователя.", default="general")}
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "Alfa News Analytics API",
            "version": "1.0.0",
            "description": "Локальный API через Next BFF. company_id/source_record_id/user_id задают контекст прототипа, не банковскую авторизацию. POST /analysis, /chat и /insight могут вызвать платный LLM-шлюз; другие методы используют сохранённые данные.",
        },
        "servers": [{"url": "/api/live", "description": "Next BFF (адрес текущего приложения)"}],
        "tags": [{"name": name} for name in ("Данные", "Профиль", "Агент", "Источники", "Сценарии", "Состояние")],
        "components": {"schemas": {
            "Error": {"type": "object", "required": ["error"], "properties": {"error": {"type": "string"}}},
            "JobAccepted": {"type": "object", "required": ["run_id", "cached", "status"], "properties": {
                "run_id": {"type": "string"}, "cached": {"type": "boolean"},
                "status": {"type": "string", "enum": ["queued", "running", "complete", "error", "interrupted"]},
            }},
            "Health": {"type": "object", "required": ["ok", "counts", "dataset_kind", "llm_available"], "properties": {
                "ok": {"type": "boolean"}, "counts": {"type": "object", "additionalProperties": {"type": "integer"}},
                "dataset_kind": {"type": "string", "enum": ["synthetic", "collected"]},
                "llm_available": {"type": "boolean"}, "agent_version": {"type": "string"},
                "analysis_availability": {"type": "object"}, "catalog_publication": {"type": "object"},
            }},
            "Run": {"type": "object", "required": ["id", "company", "record_id", "user", "article", "status", "steps"], "properties": {
                "id": {"type": "string"}, "company": {"type": "string"}, "record_id": {"type": "string"},
                "user": {"type": "string"}, "article": {"type": "string"}, "role": {"type": "string"},
                "status": {"type": "string", "enum": ["queued", "running", "complete", "error", "interrupted"]},
                "question": {"type": "string"}, "result": {"type": "object", "nullable": True},
                "steps": {"type": "array", "items": {"type": "object"}},
            }},
        }},
        "paths": {
            "/health": {"get": get("Состояние каталога, сервиса и доступности анализа", tag="Состояние", response=model_response("Health", "Состояние сервиса."))},
            "/companies": {"get": get("Поиск компаний", [parameter("q", "ID или ОКВЭД."), parameter("limit", "Максимум результатов.", kind="integer", default=25)])},
            "/company": {"get": get("Факты и provenance профиля", [COMPANY, RECORD], tag="Профиль")},
            "/feed": {"get": get("Персональная новостная лента", [*SCOPE, parameter("limit", "Число новостей.", kind="integer", minimum=1, maximum=100, default=20), parameter("request_id", "Повторяемая выдача с теми же параметрами."), parameter("scope", "Область интереса.", default="interest"), parameter("kind", "Тип материала.", default="all"), parameter("mode", "Режим выдачи.", default="ranked"), parameter("role", "Роль пользователя."), parameter("include_review", "Включить кандидатов на проверку.", kind="boolean", default=False)])},
            "/article": {"get": get("Новость по Article ID", [parameter("article_id", "Канонический Article ID.", required=True)])},
            "/news": {"get": get("Поиск новостей", [parameter("q", "Поисковая строка."), parameter("kind", "Тип материала.", default="all"), parameter("offset", "Смещение.", kind="integer", default=0), parameter("limit", "Число результатов.", kind="integer", default=30)])},
            "/insight": {
                "get": get("Сохранённый контекст статьи и компании", [COMPANY, RECORD, parameter("article_id", "Канонический Article ID.", required=True), parameter("role", "Роль пользователя.", default="general")], tag="Агент"),
                "post": post("Запустить персональный разбор", ["article_id"], {**article, **role}, tag="Агент", status="202", description="Создаёт асинхронный run; может вызвать платный LLM-шлюз."),
            },
            "/profile": {
                "get": get("Роль, темы и состояние профиля", SCOPE, tag="Профиль"),
                "post": post("Сохранить роль и темы", optional={**role, "topic_ids": {"type": "array", "items": {"type": "string"}}}, tag="Профиль"),
            },
            "/saved": {"get": get("Сохранённые статьи", SCOPE, tag="Профиль")},
            "/events": {"post": post("Записать реакцию на статью", ["article_id", "kind", "event_id"], {**article, "kind": field("Тип реакции."), "event_id": field("Уникальный ID события." )}, tag="Профиль")},
            "/context": {
                "get": get("Контекст и явные уточнения пользователя", SCOPE, tag="Профиль"),
                "post": post("Добавить или удалить уточнение", optional={"text": field("Текст нового уточнения."), "delete_id": field("ID уточнения для удаления.")}, tag="Профиль", description="Укажите text для добавления или delete_id для удаления."),
            },
            "/analysis": {"post": post("Запустить разбор новости", ["article_id"], {**article, **role}, tag="Агент", status="202", description="Возвращает run_id; выполнение асинхронно и может вызвать платный LLM-шлюз.")},
            "/chat": {"post": post("Задать вопрос к завершённому разбору", ["article_id", "parent_run_id"], {**article, **role, "question": field("Уточняющий вопрос."), "parent_run_id": field("ID завершённого родительского run.")}, tag="Агент", status="202", description="Создаёт дочерний run; может вызвать платный LLM-шлюз.")},
            "/runs": {"get": get("История запусков", SCOPE, tag="Агент")},
            "/run": {"get": get("Статус, результат и шаги запуска", [*SCOPE, parameter("run_id", "ID запуска.", required=True)], tag="Агент", response=model_response("Run", "Детали запуска."))},
            "/review": {"post": post("Оценить разбор", ["run_id", "rating"], {"run_id": field("ID запуска."), "rating": field("Оценка.", enum=["useful", "incorrect", "needs_review"]), "note": field("Комментарий.")}, tag="Агент")},
            "/metrics": {"get": get("Наблюдаемые метрики профиля", SCOPE, tag="Агент")},
            "/bank-sources": {"get": get("Банковские документы и поиск фрагментов", [parameter("q", "Поисковый запрос."), parameter("as_of", "Дата среза ISO 8601; по умолчанию сейчас.", format="date-time")], tag="Источники")},
            "/bank-file": {"get": get("Оригинальный банковский PDF", [parameter("document_id", "ID документа.", required=True)], tag="Источники", response={"description": "PDF-документ.", "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}}})},
            "/scenario": {"post": post("Посчитать процентный или валютный сценарий", ["parameters"], {"parameters": {"oneOf": [{"$ref": "#/components/schemas/LoanParameters"}, {"$ref": "#/components/schemas/FxParameters"}]}}, tag="Сценарии")},
            "/scenarios": {"get": get("История сценариев", SCOPE, tag="Сценарии")},
        },
    }


_SPEC = specification()
_SPEC["components"]["schemas"].update({
    "LoanParameters": {
        "type": "object", "required": ["kind", "currency", "principal", "days", "basis", "rate_type", "acknowledge_assumptions"],
        "properties": {
            "kind": {"type": "string", "enum": ["loan"]}, "currency": {"type": "string"},
            "principal": {"type": "string", "description": "Сумма договора, введённая пользователем."},
            "days": {"type": "integer", "minimum": 1, "maximum": 3660},
            "basis": {"type": "integer", "enum": [360, 365]},
            "rate_type": {"type": "string", "enum": ["fixed", "floating"]},
            "fixed_rate": {"type": "string"}, "benchmark_base": {"type": "string"},
            "benchmark_scenario": {"type": "string"}, "spread": {"type": "string"},
            "acknowledge_assumptions": {"type": "boolean", "enum": [True]},
        },
    },
    "FxParameters": {
        "type": "object", "required": ["kind", "currency", "amount", "rate_base", "rate_scenario", "flow", "acknowledge_assumptions"],
        "properties": {
            "kind": {"type": "string", "enum": ["fx"]}, "currency": {"type": "string", "enum": ["USD", "EUR", "CNY"]},
            "amount": {"type": "string"}, "rate_base": {"type": "string"}, "rate_scenario": {"type": "string"},
            "flow": {"type": "string", "enum": ["revenue", "expense"]},
            "acknowledge_assumptions": {"type": "boolean", "enum": [True]},
        },
    },
})


def openapi():
    return deepcopy(_SPEC)
