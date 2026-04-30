import os
import json
import subprocess
import logging
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from openai import OpenAI

# --- Настройка логирования ---
logger = logging.getLogger("Ouroborus")
logger.setLevel(logging.INFO)

log_handler = RotatingFileHandler(
    "agent.log", 
    maxBytes=5*1024*1024, 
    backupCount=3, 
    encoding="utf-8"
)
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
log_handler.setFormatter(log_formatter)
logger.addHandler(log_handler)

logger.info("=== Запуск агента Ouroborus ===")
# -----------------------------

load_dotenv()

HISTORY_FILE = "chat_history.json"
MODELS_CONFIG = {}
counter = 1

# --- Функции работы с памятью (JSON) ---
def load_history():
    """Загружает историю из файла или возвращает стартовый системный промпт"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
                logger.info(f"История загружена: {len(history)} сообщений.")
                return history
        except Exception as e:
            logger.error(f"Ошибка чтения history.json: {e}. Создана новая история.")
            print("[-] Ошибка чтения файла истории. Начинаем с чистого листа.")
            
    return [{"role": "system", "content": "Ты — полезный, лаконичный и технически подкованный ИИ-ассистент."}]

def save_history(msgs):
    """Сохраняет текущий список сообщений в файл"""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(msgs, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения истории: {e}")
        print("[-] Не удалось сохранить историю в файл.")
# ---------------------------------------

# Парсинг провайдеров
providers = set()
for key in os.environ:
    if key.startswith("API_") and key.endswith("_KEY"):
        provider_name = key[4:-4]
        providers.add(provider_name)

for provider in sorted(providers):
    api_key = os.getenv(f"API_{provider}_KEY")
    base_url = os.getenv(f"API_{provider}_URL")
    models_str = os.getenv(f"API_{provider}_MODELS")

    if not api_key or not models_str:
        continue
    
    model_list = [m.strip() for m in models_str.split(",")]
    for model_name in model_list:
        MODELS_CONFIG[str(counter)] = {
            "name": f"{provider} - {model_name}",
            "base_url": base_url,
            "model": model_name,
            "api_key": api_key
        }
        counter += 1

# Загружаем историю переписки при старте (вместо жестко заданного массива)
messages = load_history()

def setup_client(choice_id):
    config = MODELS_CONFIG.get(choice_id)
    if not config:
        return None, None

    client = OpenAI(
        api_key=config["api_key"],
        base_url=config["base_url"]
    )
    return client, config

def sync_with_git(commit_message="Auto-update from Ouroborus agent"):
    print("\n[Git] Запуск синхронизации...")
    logger.info(f"Запуск синхронизации Git. Коммит: {commit_message}")
    try:
        subprocess.run(["git", "add", "."], check=True, capture_output=True)
        
        status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
        if not status.stdout.strip():
            print("[Git] Нет новых изменений для отправки.")
            logger.info("Git: Нет изменений для коммита.")
            return

        subprocess.run(["git", "commit", "-m", commit_message], check=True, capture_output=True)
        print("[Git] Отправка на удаленный сервер...")
        subprocess.run(["git", "push"], check=True, capture_output=True, text=True)
        
        print("[*] Успешно синхронизировано с репозиторием!")
        logger.info("Git: Успешная синхронизация.")
        
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.strip() if getattr(e, 'stderr', None) else str(e)
        print(f"[-] Ошибка при работе с Git. Подробности в логе.")
        logger.error(f"Git Error: {error_msg}")
    except FileNotFoundError:
        print("[-] Утилита git не найдена в системе.")
        logger.error("Git Error: Утилита git не найдена.")

def print_menu():
    print("\n--- Доступные модели ---")
    if not MODELS_CONFIG:
        print("Модели не найдены. Проверь файл .env!")
    for key, config in MODELS_CONFIG.items():
        print(f"[{key}] {config['name']}")
    print("------------------------")

current_client, current_config = setup_client("1")

print("=== Агент Ouroborus запущен ===")
if current_config:
    print(f"Текущая модель: {current_config['name']}")
    logger.info(f"Выбрана стартовая модель: {current_config['name']}")
else:
    print("[-] Конфигурация не загружена. Проверь .env файл.")
    logger.warning("Конфигурация моделей не загружена.")
    
print("Команды: 'exit' - выход, '/switch' - смена модели, '/git [сообщение]' - бэкап кода, '/clear' - очистка памяти")

while True:
    user_input = input("\nТы: ")
    
    if not user_input.strip():
        continue

    if user_input.lower() in ['exit', 'quit', 'выход']:
        print("Завершение работы...")
        logger.info("Штатное завершение работы агента.")
        break

    # Команда для очистки истории, если контекст стал слишком большим
    if user_input.lower() == '/clear':
        messages = [{"role": "system", "content": "Ты — полезный, лаконичный и технически подкованный ИИ-ассистент."}]
        save_history(messages)
        print("[*] Память агента очищена.")
        logger.info("Память очищена пользователем.")
        continue

    if user_input.lower().startswith('/git'):
        parts = user_input.split(maxsplit=1)
        commit_msg = parts[1] if len(parts) > 1 else "Auto-commit: update agent.py"
        sync_with_git(commit_msg)
        continue 
        
    if user_input.lower() == '/switch':
        print_menu()
        choice = input("Выбери номер модели (или Enter для отмены): ")
        if choice in MODELS_CONFIG:
            new_client, new_config = setup_client(choice)
            if new_client:
                current_client = new_client
                current_config = new_config
                print(f"[*] Переключено на: {current_config['name']}")
                logger.info(f"Переключение модели на: {current_config['name']}")
        else:
            print("[-] Отмена или неверный выбор.")
        continue 

    if not current_client:
        print("[-] Модель не настроена. Введи /switch для выбора.")
        continue

    messages.append({"role": "user", "content": user_input})
    logger.info(f"User: {user_input}")

    try:
        response = current_client.chat.completions.create(
            model=current_config["model"],
            messages=messages,
            temperature=0.7
        )
        
        answer = response.choices[0].message.content
        print(f"\nАгент [{current_config['name']}]: {answer}")
        
        messages.append({"role": "assistant", "content": answer})
        logger.info(f"Agent [{current_config['model']}]: {answer}")
        
        # Сохраняем обновленный контекст в файл
        save_history(messages)
        
    except Exception as e:
        print(f"\n[Ошибка API]: Подробности записаны в лог.")
        logger.error(f"API Error ({current_config['name']}): {str(e)}", exc_info=True)
        messages.pop()
