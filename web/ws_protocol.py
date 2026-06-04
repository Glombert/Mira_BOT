"""web/ws_protocol.py — единый контракт WS/REST между сервером и клиентами.

Зачем: формы сообщений раньше были продублированы руками в Python (web/app.py)
и в TypeScript (clients/packages/shared/src/types/index.ts). Рассинхрон → тихие
баги. Теперь это **единственный источник истины** на стороне сервера (откуда
сообщения и рождаются), а тест tests/test_ws_protocol.py сверяет, что набор
типов здесь и в TS совпадает — любой дрейф валит тесты.

Модуль намеренно без FastAPI/Starlette — чтобы оставаться легко-тестируемым и
импортируемым из тестов без поднятия всего стека (как web/security.py).

Использование на сервере:
    from web.ws_protocol import Thought, ws_payload
    await websocket.send_json(ws_payload(Thought(content="…")))

ws_payload(model) гарантирует: лишние None не уходят на провод (exclude_none),
а тип сообщения всегда соответствует объявленному контракту.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Вспомогательные структуры
# ---------------------------------------------------------------------------

class SidebarCounts(BaseModel):
    files: int | None = None
    reminders_today: int | None = None
    tasks: int | None = None
    users: int | None = None
    rituals: int | None = None
    evolutions: int | None = None


class Attachment(BaseModel):
    name: str
    size: int
    # Сервер кладёт папку (inbox/output) — клиент строит по ней URL скачивания.
    dir: str | None = None


class MessageCard(BaseModel):
    # Поле уезжает на провод как "list" (контракт TS); в Python зовём list_,
    # чтобы не затенять встроенный list в аннотации соседних полей.
    model_config = ConfigDict(populate_by_name=True)
    kind: Literal["memory", "event", "backup"]
    label: str
    fact: str | None = None
    list_: list[str] | None = Field(default=None, alias="list")


class FileEntry(BaseModel):
    name: str
    dir: str
    size: int


class UserEntry(BaseModel):
    id: str
    name: str
    status: str


class ProfileData(BaseModel):
    id: str
    name: str
    role: str
    status: str
    timezone: str
    telegram: str
    about_role: str
    about_project: str
    summary: str
    gdrive_linked: bool
    gdrive_email: str
    memory_facts: int
    conversations: int
    days_together: int
    onboarded: bool
    addressing: str
    address_form: str
    manner: list[str]
    origin: str
    occupation: str
    notes: str
    manner_options: list[str]
    filled_by_mira: list[str]
    version: str


class ProfileForm(BaseModel):
    addressing: str | None = None
    address_form: str | None = None
    manner: list[str] | None = None
    origin: str | None = None
    occupation: str | None = None
    notes: str | None = None
    timezone: str | None = None


# ---------------------------------------------------------------------------
# Сервер → клиент
# ---------------------------------------------------------------------------

class Ready(BaseModel):
    type: Literal["ready"] = "ready"
    name: str
    is_owner: bool | None = None
    is_approved: bool | None = None
    gdrive_authorized: bool | None = None
    gdrive_email: str | None = None
    permissions: list[str] | None = None
    counts: SidebarCounts | None = None


class ApprovalRequest(BaseModel):
    type: Literal["approval_request"] = "approval_request"
    user_id: str
    name: str
    source: str


class PermissionsUpdate(BaseModel):
    type: Literal["permissions_update"] = "permissions_update"
    is_owner: bool | None = None
    is_approved: bool | None = None
    gdrive_authorized: bool | None = None
    gdrive_email: str | None = None
    permissions: list[str] | None = None


class AuthRequired(BaseModel):
    type: Literal["auth_required"] = "auth_required"
    bot: str


class Pong(BaseModel):
    type: Literal["pong"] = "pong"


class Thinking(BaseModel):
    type: Literal["thinking"] = "thinking"


class Thought(BaseModel):
    type: Literal["thought"] = "thought"
    content: str


class Message(BaseModel):
    type: Literal["message"] = "message"
    content: str
    attachments: list[Attachment] | None = None
    cards: list[MessageCard] | None = None


class SystemMessage(BaseModel):
    type: Literal["system"] = "system"
    content: str


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    content: str


class Files(BaseModel):
    type: Literal["files"] = "files"
    files: list[FileEntry]


class GdriveAuthUrl(BaseModel):
    type: Literal["gdrive_auth_url"] = "gdrive_auth_url"
    url: str


class UsersList(BaseModel):
    type: Literal["users_list"] = "users_list"
    users: list[UserEntry]


class Learned(BaseModel):
    type: Literal["learned"] = "learned"
    insight: str


class ProfileDataMessage(BaseModel):
    type: Literal["profile_data"] = "profile_data"
    profile: ProfileData


class ProfileSaved(BaseModel):
    type: Literal["profile_saved"] = "profile_saved"


# --- Owner-дашборды: структурные данные для экранов Aurora ---

class MetricsModelStat(BaseModel):
    model: str
    calls: int
    tokens: int
    cost: float


class MetricsDayStat(BaseModel):
    day: str
    calls: int
    cost: float


class MetricsData(BaseModel):
    type: Literal["metrics_data"] = "metrics_data"
    days: int
    total_calls: int
    total_tokens: int
    cost_est: float
    by_model: list[MetricsModelStat]
    by_day: list[MetricsDayStat]


class RitualEntry(BaseModel):
    id: str
    name: str
    description: str
    schedule: str
    days: list[bool]              # пн..вс (7) — для мини-календаря
    enabled: bool
    last_run: str | None = None
    next_run: str | None = None


class RitualsData(BaseModel):
    type: Literal["rituals_data"] = "rituals_data"
    rituals: list[RitualEntry]


class ReminderEntry(BaseModel):
    id: str
    title: str
    at: str                       # trigger_at (ISO)
    done: bool
    # gcal/repeat/mira_note пока не трекаются в таблице reminders — дефолты,
    # чтобы фронт §5 типизировался. Появятся, когда добавим поля в БД.
    gcal: bool = False
    repeat: str | None = None
    mira_note: str | None = None


class RemindersData(BaseModel):
    type: Literal["reminders_data"] = "reminders_data"
    reminders: list[ReminderEntry]


class TaskEntry(BaseModel):
    id: str
    message: str
    at: str                       # trigger_at
    status: str


class TasksData(BaseModel):
    type: Literal["tasks_data"] = "tasks_data"
    tasks: list[TaskEntry]


class BackupEntry(BaseModel):
    id: str
    created_at: str
    size: int = 0
    type: str = "auto"
    # Снапшоты не хранят пофактовые счётчики — отдаём ТЕКУЩИЕ (для всех одинаковы).
    fact_count: int = 0
    note_count: int = 0
    is_latest: bool = False


class BackupsData(BaseModel):
    type: Literal["backups_data"] = "backups_data"
    schedule: str
    storage: str
    backups: list[BackupEntry]


SERVER_MESSAGES: tuple[type[BaseModel], ...] = (
    Ready, ApprovalRequest, PermissionsUpdate, AuthRequired, Pong,
    Thinking, Thought, Message, SystemMessage, ErrorMessage, Files,
    GdriveAuthUrl, UsersList, Learned, ProfileDataMessage, ProfileSaved,
    MetricsData, RitualsData, RemindersData, TasksData, BackupsData,
)


# ---------------------------------------------------------------------------
# Клиент → сервер
# ---------------------------------------------------------------------------

class Ping(BaseModel):
    type: Literal["ping"] = "ping"


class Command(BaseModel):
    type: Literal["command"] = "command"
    cmd: str


class ProfileSave(BaseModel):
    type: Literal["profile_save"] = "profile_save"
    form: ProfileForm


class ChatMessage(BaseModel):
    """Обычное сообщение чата — единственное без поля type (по контракту)."""
    content: str
    attachment: str | None = None
    attachments: list[str] | None = None
    mode: Literal["chat", "tech"] | None = None


# Клиентские сообщения с дискриминатором type. ChatMessage — бестиповый, обрабатывается отдельно.
CLIENT_MESSAGES_TYPED: tuple[type[BaseModel], ...] = (Ping, Command, ProfileSave)


def _type_literal(model: type[BaseModel]) -> str:
    """Достаёт значение Literal из поля `type` модели."""
    return model.model_fields["type"].default


SERVER_MESSAGE_TYPES: frozenset[str] = frozenset(_type_literal(m) for m in SERVER_MESSAGES)
CLIENT_MESSAGE_TYPES: frozenset[str] = frozenset(_type_literal(m) for m in CLIENT_MESSAGES_TYPED)


# ---------------------------------------------------------------------------
# REST-ответы
# ---------------------------------------------------------------------------

class AuthResult(BaseModel):
    ok: bool
    session: str | None = None
    name: str | None = None
    is_new: bool | None = None
    error: str | None = None


class HealthStatus(BaseModel):
    status: str
    bot_alive: bool
    web_alive: bool


class UploadResult(BaseModel):
    ok: bool
    filename: str
    size: int


# ---------------------------------------------------------------------------
# Сериализация на провод
# ---------------------------------------------------------------------------

def ws_payload(model: BaseModel) -> dict:
    """Готовит dict для websocket.send_json: без None-полей, валидный по контракту.

    by_alias=True — чтобы поля с алиасами (MessageCard.list_) уезжали под
    контрактным именем; на моделях без алиасов поведение не меняется.
    """
    return model.model_dump(exclude_none=True, by_alias=True)
