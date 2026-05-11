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
import logging
import threading
from pathlib import Path

logger = logging.getLogger("Ouroborus")

# Scope: drive.file — приложение видит только файлы которые само создало
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Redirect URI: на VPS — веб-колбэк, локально — localhost
REDIRECT_URI = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8080")

# Папка для токенов
GDRIVE_TOKENS_DIR = os.path.join("memory", "gdrive")

os.makedirs(GDRIVE_TOKENS_DIR, exist_ok=True)


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

def _token_path(user_id: str) -> str:
    return os.path.join(GDRIVE_TOKENS_DIR, f"{user_id}.json")


def _load_token(user_id: str) -> dict | None:
    """Загружает токены пользователя (расшифровывает если нужно)."""
    path = _token_path(user_id)
    if not os.path.exists(path):
        return None
    try:
        import memory_crypto
        return memory_crypto.load_json(path)
    except Exception as e:
        logger.warning(f"gdrive: ошибка загрузки токена {user_id}: {e}")
        return None


def _save_token(user_id: str, token_data: dict) -> None:
    """Сохраняет токены пользователя (шифрует если настроено)."""
    import memory_crypto
    try:
        memory_crypto.save_json(_token_path(user_id), token_data)
    except Exception as e:
        logger.error(f"gdrive: ошибка сохранения токена {user_id}: {e}")


def _delete_token(user_id: str) -> None:
    """Удаляет токены пользователя."""
    path = _token_path(user_id)
    if os.path.exists(path):
        os.remove(path)


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
        flow = Flow.from_client_secrets_file(
            _credentials_path(),
            scopes=SCOPES,
            redirect_uri=REDIRECT_URI,
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
