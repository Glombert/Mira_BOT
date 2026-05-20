"""
tools/fcm_tools.py — отправка push-уведомлений через Firebase Cloud Messaging.

Сервер-сайд использует Firebase Admin SDK с service account JSON,
сгенерированным в Firebase Console → Service Accounts. Путь к файлу —
из env FCM_SERVICE_ACCOUNT_PATH (по умолчанию .firebase-service-account.json
в корне репо).

Если файла нет или firebase-admin не установлен — все push-вызовы становятся
no-op (без ошибок), и notify_owner просто доставляет в Telegram как раньше.
Это позволяет работать без FCM на dev-окружении.
"""

import os
import logging
from tools import db

logger = logging.getLogger("Ouroboros")

_app = None
_init_attempted = False
_disabled_reason: str | None = None


def _service_account_path() -> str:
    return os.getenv(
        "FCM_SERVICE_ACCOUNT_PATH",
        os.path.join(os.path.dirname(__file__), "..", ".firebase-service-account.json"),
    )


def _ensure_init() -> bool:
    """Ленивая инициализация Firebase Admin SDK.

    Не падает при отсутствии файла / пакета — возвращает False,
    notify_user_push становится no-op.
    """
    global _app, _init_attempted, _disabled_reason
    if _app is not None:
        return True
    if _init_attempted:
        return False
    _init_attempted = True

    path = _service_account_path()
    if not os.path.isfile(path):
        _disabled_reason = f"FCM disabled: нет файла service account по пути {path}"
        logger.info(_disabled_reason)
        return False
    try:
        import firebase_admin
        from firebase_admin import credentials
        cred = credentials.Certificate(path)
        # initialize_app кидает ValueError если default уже инициализирован
        # (например при reload). Подхватываем существующий.
        try:
            _app = firebase_admin.initialize_app(cred)
        except ValueError:
            _app = firebase_admin.get_app()
        logger.info("FCM Admin SDK инициализирован")
        return True
    except ImportError:
        _disabled_reason = "FCM disabled: firebase-admin не установлен (pip install firebase-admin)"
        logger.warning(_disabled_reason)
        return False
    except Exception as e:
        _disabled_reason = f"FCM disabled: {e}"
        logger.warning(_disabled_reason)
        return False


def send_push(user_id: str, title: str, body: str, data: dict | None = None) -> int:
    """Отправляет push всем устройствам пользователя.

    Возвращает количество успешно отправленных сообщений (0 если FCM
    выключен или у пользователя нет токенов). Не кидает исключений —
    оборачивает все ошибки в лог и возвращает 0.
    """
    if not _ensure_init():
        return 0
    tokens_meta = db.list_push_tokens(user_id)
    if not tokens_meta:
        return 0
    try:
        from firebase_admin import messaging
    except ImportError:
        return 0

    # FCM data-поля должны быть string. Конвертим всё в str.
    data_str = {k: str(v) for k, v in (data or {}).items()}

    sent = 0
    for entry in tokens_meta:
        token = entry["token"]
        try:
            message = messaging.Message(
                notification=messaging.Notification(title=title, body=body),
                data=data_str,
                token=token,
                android=messaging.AndroidConfig(
                    priority="high",
                    notification=messaging.AndroidNotification(
                        channel_id="mira_default",
                        # icon/color можно добавить когда соберём design;
                        # пока используется дефолтный из манифеста.
                    ),
                ),
            )
            messaging.send(message)
            sent += 1
        except Exception as e:
            # FCM возвращает Unregistered / InvalidArgument для битых токенов —
            # удаляем их из БД, чтобы не молотить.
            err_class = type(e).__name__
            if err_class in ("UnregisteredError", "SenderIdMismatchError"):
                db.delete_push_token(user_id, token)
                logger.info(f"FCM: удалён мёртвый токен пользователя {user_id} ({err_class})")
            else:
                logger.warning(f"FCM send_push: {err_class}: {e}")
    return sent
