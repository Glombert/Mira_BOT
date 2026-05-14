"""
tools/gdrive_tools.py — персональный Google Drive для пользователей.

OAuth 2.0 для Telegram: каждый пользователь авторизует свой Google-аккаунт.
Токены хранятся в memory/gdrive/{user_id}.json (зашифрованы Fernet).

Команды Telegram:
    /google_login  — начать авторизацию (получить ссылку)
    /google_auth   — обменять код на токены
    /google_logout — отвязать аккаунт
    /gdrive        — список файлов на Drive
    /gdrive_get    — скачать файл с Drive

Инструменты для агента (TOOL_SCHEMAS):
    gdrive_list(path)   — список файлов в папке Drive
    gdrive_read(path)   — прочитать/скачать файл с Drive
    gdrive_write(path)  — загрузить файл на Drive

Авто-загрузка: когда авторизованный пользователь отправляет документ боту,
он автоматически дублируется в корень Google Drive.
"""

import os
import io
import json
import time
import logging
import threading
from pathlib import Path

logger = logging.getLogger("Ouroborus")

# Scopes: Drive (file-level), Calendar (events), Sheets (full access)
SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/spreadsheets',
]

# Redirect URI: на VPS — веб-колбэк, локально — localhost
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080")

# Папка для токенов и временных verifier'ов PKCE
GDRIVE_TOKENS_DIR = os.path.join("memory", "gdrive")

os.makedirs(GDRIVE_TOKENS_DIR, exist_ok=True)


def _verifier_path(user_id: str) -> str:
    return os.path.join(GDRIVE_TOKENS_DIR, f".verifier_{user_id}")


def _save_verifier(user_id: str, verifier: str) -> None:
    """Сохраняет PKCE code_verifier на диск зашифрованным (переживает рестарт)."""
    try:
        import memory_crypto
        memory_crypto.save_json(
            _verifier_path(user_id),
            {"verifier": verifier, "at": time.time()},
        )
        try:
            os.chmod(_verifier_path(user_id), 0o600)
        except Exception:
            pass
    except Exception as e:
        logger.warning(f"gdrive: не удалось сохранить verifier: {e}")


def _load_verifier(user_id: str) -> str | None:
    """Загружает и удаляет PKCE code_verifier (одноразовый, max 10 минут)."""
    path = _verifier_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        import memory_crypto
        data = memory_crypto.load_json(path)
        os.remove(path)
        if not isinstance(data, dict):
            return None
        if time.time() - data.get("at", 0) >= 600:
            return None
        return data.get("verifier")
    except Exception as e:
        logger.warning(f"gdrive: ошибка загрузки verifier: {e}")
        try:
            os.remove(path)
        except Exception:
            pass
        return None


# ---------------------------------------------------------------------------
# Конфигурация
# ---------------------------------------------------------------------------

def _credentials_path() -> str:
    return os.path.join(os.path.dirname(__file__), "..", "credentials.json")


def is_configured() -> bool:
    """Проверяет что credentials.json существует (Google Cloud настроен)."""
    return os.path.isfile(_credentials_path())


# ---------------------------------------------------------------------------
# Хранение токенов
# ---------------------------------------------------------------------------

def _load_token(user_id: str) -> dict | None:
    """Загружает токены пользователя из mira.db."""
    from tools import db
    try:
        return db.load_gdrive_token(user_id)
    except Exception as e:
        logger.warning(f"gdrive: ошибка загрузки токена {user_id}: {e}")
        return None


def _save_token(user_id: str, token_data: dict) -> None:
    """Сохраняет токены пользователя в mira.db."""
    from tools import db
    try:
        db.save_gdrive_token(user_id, token_data)
    except Exception as e:
        logger.error(f"gdrive: ошибка сохранения токена {user_id}: {e}")


def _delete_token(user_id: str) -> None:
    """Удаляет токены пользователя."""
    from tools import db
    db.delete_gdrive_token(user_id)


def is_authorized(user_id: str) -> bool:
    """Проверяет что пользователь авторизовал Google Drive."""
    token = _load_token(user_id)
    return token is not None and bool(token.get("refresh_token"))


# ---------------------------------------------------------------------------
# OAuth 2.0 Flow
# ---------------------------------------------------------------------------

def get_auth_url(state: str | None = None) -> str | None:
    """
    Генерирует URL для авторизации Google.

    Пользователь открывает ссылку, даёт разрешение, Google редиректит
    на REDIRECT_URI (VPS колбэк или localhost) с code=... и state=... в URL.

    Если state передан — Google вернёт его обратно при редиректе.
    В state кодируется user_id для авто-обмена кода на веб-колбэке.
    """
    if not is_configured():
        return None
    try:
        from google_auth_oauthlib.flow import Flow
        flow = Flow.from_client_secrets_file(
            _credentials_path(),
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
        )
        kwargs = {
            'access_type': 'offline',
            'prompt': 'consent',
        }
        if state:
            kwargs['state'] = state
        url, _ = flow.authorization_url(**kwargs)

        # Сохраняем code_verifier для PKCE на диск (переживает рестарт бота)
        if state:
            _save_verifier(state, flow.code_verifier)
        return url
    except Exception as e:
        logger.error(f"gdrive: ошибка генерации auth_url: {e}")
        return None


def exchange_code(user_id: str, code: str) -> dict:
    """
    Обменивает authorization code на access_token + refresh_token.

    Возвращает {'ok': True, 'email': '...'} или {'ok': False, 'error': '...'}.
    """
    if not is_configured():
        return {"ok": False, "error": "credentials.json не найден — настрой Google Cloud"}

    try:
        from google_auth_oauthlib.flow import Flow

        # Достаём code_verifier с диска (PKCE, переживает рестарт)
        code_verifier = _load_verifier(user_id)

        flow = Flow.from_client_secrets_file(
            _credentials_path(),
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
            code_verifier=code_verifier,
        )
        flow.fetch_token(code=code)

        credentials = flow.credentials
        token_data = {
            "refresh_token": credentials.refresh_token,
            "access_token":  credentials.token,
            "token_uri":     credentials.token_uri,
            "client_id":     credentials.client_id,
            "scopes":        list(credentials.scopes),
            "email":         getattr(credentials, 'id_token', None),
        }
        _save_token(user_id, token_data)

        # Получаем email пользователя для проверки
        email = _get_user_email(credentials.token)
        if email:
            token_data["email"] = email
            _save_token(user_id, token_data)

        logger.info(f"gdrive: пользователь {user_id} авторизован (email: {email})")
        return {"ok": True, "email": email or "неизвестно"}

    except Exception as e:
        logger.error(f"gdrive: ошибка обмена кода для {user_id}: {e}")
        return {"ok": False, "error": str(e)[:300]}


def parse_oauth_state(state: str) -> str | None:
    """
    Извлекает user_id из OAuth state параметра.
    Формат: tg_{id} или web_tg_{id}.
    """
    if state and (state.startswith("tg_") or state.startswith("web_tg_")):
        return state


def _get_user_email(access_token: str) -> str | None:
    """Получает email пользователя через Google OAuth2 userinfo."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(token=access_token)
        service = build('oauth2', 'v2', credentials=creds)
        user_info = service.userinfo().get().execute()
        return user_info.get('email')
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Клиент Google Drive
# ---------------------------------------------------------------------------

def _get_drive_service(user_id: str):
    """
    Создаёт авторизованный клиент Google Drive для пользователя.
    Возвращает (service, error_string).
    """
    if not is_configured():
        return None, "credentials.json не найден"

    token = _load_token(user_id)
    if not token or not token.get("refresh_token"):
        return None, "Не авторизован. Отправь /google_login"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=token.get("access_token"),
            refresh_token=token["refresh_token"],
            token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token.get("client_id"),
            scopes=token.get("scopes", SCOPES),
        )

        # Авто-рефреш протухшего токена
        if not creds.valid:
            try:
                creds.refresh(Request())
                token["access_token"] = creds.token
                _save_token(user_id, token)
                logger.info(f"gdrive: токен обновлён для {user_id}")
            except Exception as e:
                _delete_token(user_id)
                logger.warning(f"gdrive: не удалось обновить токен {user_id}, удалён: {e}")
                return None, "Токен протух. Отправь /google_login заново."

        service = build('drive', 'v3', credentials=creds)
        return service, None

    except Exception as e:
        logger.error(f"gdrive: ошибка создания клиента для {user_id}: {e}")
        return None, str(e)[:300]


# ---------------------------------------------------------------------------
# Операции с файлами (инструменты агента)
# ---------------------------------------------------------------------------

def _resolve_path(user_id: str, path: str) -> tuple[str | None, str | None]:
    """
    Разбирает путь: "папка/файл.txt" или ID файла.
    Возвращает (file_id, error).
    """
    # Если похоже на ID файла Google Drive (буквы+цифры, ~33 символа)
    if len(path) >= 25 and '/' not in path and not path.startswith('.'):
        return path, None

    # Иначе ищем по имени
    return None, None  # путь-имя, будем искать ниже


def gdrive_list(user_id: str, path: str = "root") -> dict:
    """
    Показывает список файлов в Google Drive пользователя.

    Аргументы:
        path — путь к папке или 'root' для корня.
               Можно передать ID папки.
    """
    service, err = _get_drive_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        # Определяем ID папки
        folder_id = "root"
        if path and path != "root":
            folder_id = _find_folder_id(service, path)
            if not folder_id:
                return {"ok": False, "error": f"Папка не найдена: {path}"}

        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query,
            pageSize=50,
            fields="files(id, name, mimeType, size, modifiedTime, webViewLink)",
        ).execute()

        files = results.get('files', [])
        formatted = []
        for f in files:
            size_str = ""
            if f.get('size'):
                size = int(f['size'])
                if size < 1024:
                    size_str = f"{size} B"
                elif size < 1024 * 1024:
                    size_str = f"{size / 1024:.1f} KB"
                else:
                    size_str = f"{size / (1024 * 1024):.1f} MB"

            is_folder = f['mimeType'] == 'application/vnd.google-apps.folder'
            formatted.append({
                "id":       f['id'],
                "name":     f['name'],
                "type":     "folder" if is_folder else "file",
                "size":     size_str,
                "modified": f.get('modifiedTime', '')[:19],
                "mime":     f.get('mimeType', ''),
            })

        logger.info(f"gdrive_list: {user_id} → {path} ({len(formatted)} элементов)")
        return {"ok": True, "path": path, "files": formatted}

    except Exception as e:
        logger.error(f"gdrive_list error: {e}")
        return {"ok": False, "error": f"Ошибка списка файлов: {e}"}


def gdrive_read(user_id: str, file_path: str) -> dict:
    """
    Скачивает файл с Google Drive пользователя в workspace/output/.

    Аргументы:
        file_path — ID файла или имя файла в корне Drive.
    """
    service, err = _get_drive_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        # Ищем файл по ID или имени
        file_id = file_path
        file_name = file_path

        if len(file_path) < 25 or '/' in file_path or '.' in file_path.split('/')[-1]:
            # Похоже на имя, а не ID — ищем
            query = f"name = '{file_path}' and trashed = false"
            results = service.files().list(q=query, pageSize=5, fields="files(id, name, size)").execute()
            found = results.get('files', [])
            if not found:
                return {"ok": False, "error": f"Файл не найден: {file_path}"}
            file_id = found[0]['id']
            file_name = found[0]['name']

        # Скачиваем содержимое
        request = service.files().get_media(fileId=file_id)
        content = request.execute()

        # Сохраняем в workspace/output/
        from agent import WORKSPACE_DIR
        output = os.path.join(WORKSPACE_DIR, user_id, "output")
        os.makedirs(output, exist_ok=True)
        dest = os.path.join(output, file_name)
        with open(dest, "wb") as f:
            f.write(content)

        size = len(content)
        logger.info(f"gdrive_read: {user_id} ← {file_name} ({size} bytes)")
        return {
            "ok": True,
            "file": file_name,
            "path": f"output/{file_name}",
            "size": size,
        }

    except Exception as e:
        logger.error(f"gdrive_read error: {e}")
        return {"ok": False, "error": f"Ошибка чтения файла: {e}"}


def gdrive_write(user_id: str, workspace_path: str, drive_folder: str = "root") -> dict:
    """
    Загружает файл из workspace пользователя на Google Drive.

    Аргументы:
        workspace_path — путь к файлу в workspace (например, "inbox/фото.jpg" или "output/отчёт.xlsx")
        drive_folder   — ID папки на Drive или "root" для корня
    """
    service, err = _get_drive_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        from agent import WORKSPACE_DIR

        # Защита: только внутри workspace пользователя
        full_path = os.path.normpath(os.path.join(WORKSPACE_DIR, user_id, workspace_path))
        if not full_path.startswith(os.path.join(WORKSPACE_DIR, user_id)):
            return {"ok": False, "error": "Доступ запрещён"}

        if not os.path.isfile(full_path):
            return {"ok": False, "error": f"Файл не найден: {workspace_path}"}

        file_name = os.path.basename(full_path)

        # Определяем MIME-тип
        import mimetypes
        mime_type, _ = mimetypes.guess_type(full_path)
        if not mime_type:
            mime_type = 'application/octet-stream'

        # Загружаем
        from googleapiclient.http import MediaFileUpload

        file_metadata = {'name': file_name}
        if drive_folder and drive_folder != "root":
            file_metadata['parents'] = [drive_folder]

        media = MediaFileUpload(full_path, mimetype=mime_type, resumable=True)
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, name, size, webViewLink',
        ).execute()

        logger.info(f"gdrive_write: {user_id} → {file_name} ({uploaded.get('id')})")
        return {
            "ok": True,
            "file": file_name,
            "drive_id": uploaded.get('id'),
            "size": int(uploaded.get('size', 0)),
        }

    except Exception as e:
        logger.error(f"gdrive_write error: {e}")
        return {"ok": False, "error": f"Ошибка записи файла: {e}"}


# ---------------------------------------------------------------------------
# Вспомогательные функции
# ---------------------------------------------------------------------------

def _find_folder_id(service, folder_name: str) -> str | None:
    """Ищет папку по имени в корне Drive. Возвращает ID или None."""
    try:
        query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        results = service.files().list(q=query, pageSize=5, fields="files(id, name)").execute()
        folders = results.get('files', [])
        return folders[0]['id'] if folders else None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Авто-загрузка в фоне
# ---------------------------------------------------------------------------

def auto_upload_to_drive(user_id: str, file_path: str) -> None:
    """
    Фоновая загрузка файла на Google Drive пользователя.

    Вызывается когда авторизованный пользователь отправляет документ боту.
    Не блокирует основной поток.
    """
    if not is_authorized(user_id):
        return

    def _upload():
        try:
            result = gdrive_write(user_id, file_path)
            if result.get("ok"):
                logger.info(f"gdrive auto-upload: {user_id} → {file_path}")
            else:
                logger.warning(f"gdrive auto-upload failed: {result.get('error')}")
        except Exception as e:
            logger.warning(f"gdrive auto-upload error: {e}")

    threading.Thread(target=_upload, daemon=True).start()


def gdrive_status(user_id: str) -> dict:
    """
    Возвращает статус привязки Google Drive для пользователя.
    """
    token = _load_token(user_id)
    if not token:
        return {"authorized": False, "reason": "Не авторизован"}
    if not token.get("refresh_token"):
        return {"authorized": False, "reason": "Токен недействителен"}
    return {
        "authorized": True,
        "email": token.get("email", "неизвестно"),
    }


# ---------------------------------------------------------------------------
# Google Calendar
# ---------------------------------------------------------------------------

def _get_calendar_service(user_id: str):
    """
    Создаёт авторизованный клиент Google Calendar API (v3).
    Возвращает (service, error_string) — как _get_drive_service.
    """
    if not is_configured():
        return None, "credentials.json не найден"

    token = _load_token(user_id)
    if not token or not token.get("refresh_token"):
        return None, "Не авторизован. Отправь /google_login"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=token.get("access_token"),
            refresh_token=token["refresh_token"],
            token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token.get("client_id"),
            scopes=token.get("scopes", SCOPES),
        )

        if not creds.valid:
            try:
                creds.refresh(Request())
                token["access_token"] = creds.token
                _save_token(user_id, token)
            except Exception as e:
                logger.warning(f"gcal: не удалось обновить токен {user_id}: {e}")
                return None, "Токен протух. Отправь /google_login заново."

        service = build('calendar', 'v3', credentials=creds)
        return service, None

    except Exception as e:
        logger.error(f"gcal: ошибка создания клиента для {user_id}: {e}")
        return None, str(e)[:300]


def gcal_list(user_id: str, max_results: int = 10, time_min: str | None = None) -> dict:
    """
    Показывает ближайшие события из основного календаря пользователя.

    Аргументы:
        max_results — сколько событий показать (по умолчанию 10)
        time_min    — с какой даты в ISO-формате (по умолчанию — сейчас)
    """
    service, err = _get_calendar_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        from datetime import datetime, timezone
        if not time_min:
            time_min = datetime.now(timezone.utc).isoformat()

        events_result = service.events().list(
            calendarId='primary',
            timeMin=time_min,
            maxResults=min(max(1, int(max_results)), 50),
            singleEvents=True,
            orderBy='startTime',
        ).execute()

        events = events_result.get('items', [])
        formatted = []
        for e in events:
            start = e.get('start', {})
            end   = e.get('end', {})
            formatted.append({
                "id":      e.get('id'),
                "summary": e.get('summary', '(без названия)'),
                "start":   start.get('dateTime') or start.get('date', ''),
                "end":     end.get('dateTime') or end.get('date', ''),
                "location": e.get('location', ''),
                "description": (e.get('description', '') or '')[:300],
            })

        return {"ok": True, "events": formatted}

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        logger.error(f"gcal_list error: {e}")
        return {"ok": False, "error": f"Ошибка чтения календаря: {e}"}


def _get_calendar_timezone(service) -> str:
    """Читает часовой пояс основного календаря пользователя. Возвращает 'Europe/Moscow' если не удалось."""
    try:
        cal = service.calendars().get(calendarId='primary').execute()
        return cal.get('timeZone', 'Europe/Moscow')
    except Exception:
        return 'Europe/Moscow'


def gcal_create(user_id: str, summary: str, start_time: str,
                end_time: str = "", description: str = "") -> dict:
    """
    Создаёт событие в календаре пользователя.
    Часовой пояс берётся из настроек Google Calendar пользователя.

    Аргументы:
        summary     — название события
        start_time  — начало в ISO-формате ("2026-05-15T14:00:00")
        end_time    — конец (если не указан — +1 час от начала)
        description — описание события
    """
    service, err = _get_calendar_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        from datetime import datetime, timedelta, timezone

        tz = _get_calendar_timezone(service)

        # Парсим start_time
        try:
            start_dt = datetime.fromisoformat(start_time)
        except ValueError:
            return {"ok": False, "error": f"Неверный формат даты: {start_time}. Используй ISO: 2026-05-15T14:00:00"}

        if end_time:
            try:
                end_dt = datetime.fromisoformat(end_time)
            except ValueError:
                end_dt = start_dt + timedelta(hours=1)
        else:
            end_dt = start_dt + timedelta(hours=1)

        event = {
            'summary': summary,
            'start': {'dateTime': start_dt.isoformat(), 'timeZone': tz},
            'end':   {'dateTime': end_dt.isoformat(),   'timeZone': tz},
        }
        if description:
            event['description'] = description[:2000]

        created = service.events().insert(calendarId='primary', body=event).execute()

        return {
            "ok": True,
            "event_id": created.get('id'),
            "summary": summary,
            "link": created.get('htmlLink', ''),
        }

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        logger.error(f"gcal_create error: {e}")
        return {"ok": False, "error": f"Ошибка создания события: {e}"}


def gcal_quick_add(user_id: str, text: str) -> dict:
    """
    Создаёт событие из естественной фразы через Google Calendar Quick Add.

    Примеры:
        "Встреча с Колей завтра в 15:00"
        "Кофе с Аней в субботу в 10 утра на Покровке"
    """
    service, err = _get_calendar_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        created = service.events().quickAdd(calendarId='primary', text=text).execute()

        return {
            "ok": True,
            "event_id": created.get('id'),
            "summary": created.get('summary', text),
            "link": created.get('htmlLink', ''),
        }

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        logger.error(f"gcal_quick_add error: {e}")
        return {"ok": False, "error": f"Не удалось создать событие: {e}"}


# ---------------------------------------------------------------------------
# Google Sheets
# ---------------------------------------------------------------------------

def _get_sheets_service(user_id: str):
    """
    Создаёт авторизованный клиент Google Sheets API (v4).
    Возвращает (service, error_string).
    """
    if not is_configured():
        return None, "credentials.json не найден"

    token = _load_token(user_id)
    if not token or not token.get("refresh_token"):
        return None, "Не авторизован. Отправь /google_login"

    try:
        from google.oauth2.credentials import Credentials
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        creds = Credentials(
            token=token.get("access_token"),
            refresh_token=token["refresh_token"],
            token_uri=token.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=token.get("client_id"),
            scopes=token.get("scopes", SCOPES),
        )

        if not creds.valid:
            try:
                creds.refresh(Request())
                token["access_token"] = creds.token
                _save_token(user_id, token)
            except Exception as e:
                logger.warning(f"gsheet: не удалось обновить токен {user_id}: {e}")
                return None, "Токен протух. Отправь /google_login заново."

        service = build('sheets', 'v4', credentials=creds)
        return service, None

    except Exception as e:
        logger.error(f"gsheet: ошибка создания клиента для {user_id}: {e}")
        return None, str(e)[:300]


def gsheet_read(user_id: str, spreadsheet_id: str,
                sheet_range: str = "A1:Z100") -> dict:
    """
    Читает данные из Google Sheets пользователя.

    Аргументы:
        spreadsheet_id — ID таблицы (из URL: docs.google.com/spreadsheets/d/{ID}/edit)
        sheet_range    — диапазон в A1-нотации (например "Лист1!A1:D20" или "A1:Z100")
    """
    service, err = _get_sheets_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
        ).execute()

        values = result.get('values', [])
        return {
            "ok": True,
            "spreadsheet_id": spreadsheet_id,
            "range": sheet_range,
            "rows": len(values),
            "values": values,
        }

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        if 'not found' in err_str:
            return {"ok": False, "error": f"Таблица не найдена. Проверь ID: {spreadsheet_id}"}
        logger.error(f"gsheet_read error: {e}")
        return {"ok": False, "error": f"Ошибка чтения таблицы: {e}"}


def gsheet_write(user_id: str, spreadsheet_id: str, sheet_range: str,
                 values: list) -> dict:
    """
    Записывает данные в Google Sheets пользователя.

    Аргументы:
        spreadsheet_id — ID таблицы
        sheet_range    — диапазон (например "Лист1!A1")
        values         — список списков со значениями (например [["Имя", "Возраст"], ["Аня", "25"]])
    """
    service, err = _get_sheets_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        body = {'values': values}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=sheet_range,
            valueInputOption='USER_ENTERED',
            body=body,
        ).execute()

        return {
            "ok": True,
            "spreadsheet_id": spreadsheet_id,
            "range": result.get('updatedRange', sheet_range),
            "updated_cells": result.get('updatedCells', 0),
        }

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        logger.error(f"gsheet_write error: {e}")
        return {"ok": False, "error": f"Ошибка записи в таблицу: {e}"}


def gsheet_create(user_id: str, title: str) -> dict:
    """
    Создаёт новую Google Sheets таблицу на Drive пользователя.

    Аргументы:
        title — название новой таблицы
    """
    service, err = _get_sheets_service(user_id)
    if err:
        return {"ok": False, "error": err}

    try:
        spreadsheet = service.spreadsheets().create(body={
            'properties': {'title': title},
        }).execute()

        return {
            "ok": True,
            "spreadsheet_id": spreadsheet.get('spreadsheetId'),
            "title": title,
            "url": spreadsheet.get('spreadsheetUrl', ''),
        }

    except Exception as e:
        err_str = str(e).lower()
        if 'insufficient' in err_str or 'scope' in err_str:
            return {"ok": False, "error": "Недостаточно прав. Обнови авторизацию: /google_login"}
        logger.error(f"gsheet_create error: {e}")
        return {"ok": False, "error": f"Ошибка создания таблицы: {e}"}
