"""JSON-схемы инструментов для function calling.

Вынесено из agent.py чтобы:
- agent.py был читаемым (раньше 683 строки данных в середине файла)
- схемы можно было импортировать без загрузки всего агента
- легче добавлять/править инструменты без скролла мимо логики

agent.py реэкспортирует TOOL_SCHEMAS для обратной совместимости.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": (
                "Показывает список файлов и папок в рабочем пространстве пользователя. "
                "Используй когда нужно узнать какие файлы есть у пользователя."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "subdir": {
                        "type": "string",
                        "description": (
                            "Подпапка внутри workspace (например 'inbox' или 'output'). "
                            "Если не указано — показывает корень workspace."
                        )
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": (
                "Читает содержимое текстового файла из workspace пользователя. "
                "Работает только с текстовыми файлами (не Excel, не картинки). "
                "Максимальный размер файла — 1 MB."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": (
                            "Путь к файлу относительно workspace пользователя. "
                            "Например: 'inbox/notes.txt' или 'output/result.py'"
                        )
                    }
                },
                "required": ["relative_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": (
                "Записывает текст в файл в workspace пользователя. "
                "По умолчанию не перезаписывает существующие файлы — "
                "нужно явно передать overwrite=true если файл уже есть."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": (
                            "Путь к файлу относительно workspace. "
                            "Папки создаются автоматически. "
                            "Пример: 'output/result.txt'"
                        )
                    },
                    "content": {
                        "type": "string",
                        "description": "Текст для записи в файл."
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": (
                            "Разрешить перезапись если файл уже существует. "
                            "По умолчанию false."
                        )
                    }
                },
                "required": ["relative_path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": (
                "Выполняет Python-код в отдельном процессе и возвращает вывод. "
                "Используй для вычислений, обработки данных, проверки логики. "
                "Таймаут: 30 секунд. Рабочая директория: workspace пользователя."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python-код для выполнения."
                    }
                },
                "required": ["code"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "excel_read",
            "description": (
                "Читает Excel-файл (.xlsx) из workspace пользователя. "
                "Возвращает заголовки и строки данных. "
                "Максимум 200 строк за раз."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Путь к .xlsx файлу относительно workspace. Например: 'inbox/data.xlsx'"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Имя листа. Если не указано — читается первый лист."
                    }
                },
                "required": ["relative_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "excel_write",
            "description": (
                "Создаёт Excel-файл (.xlsx) в workspace пользователя. "
                "Принимает заголовки и строки данных. "
                "По умолчанию не перезаписывает существующий файл."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "relative_path": {
                        "type": "string",
                        "description": "Путь к .xlsx файлу относительно workspace. Например: 'output/report.xlsx'"
                    },
                    "headers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Список заголовков столбцов. Например: ['Имя', 'Возраст', 'Email']"
                    },
                    "rows": {
                        "type": "array",
                        "items": {"type": "array"},
                        "description": "Список строк данных. Например: [['Иван', 30, 'ivan@mail.ru'], ['Мария', 25, 'maria@mail.ru']]"
                    },
                    "sheet_name": {
                        "type": "string",
                        "description": "Имя листа. По умолчанию 'Sheet1'."
                    },
                    "overwrite": {
                        "type": "boolean",
                        "description": "Разрешить перезапись если файл уже существует. По умолчанию false."
                    }
                },
                "required": ["relative_path", "headers", "rows"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_template",
            "description": (
                "Сохраняет шаблон повторяющейся задачи пользователя. "
                "Используй когда пользователь делает одно и то же несколько раз — "
                "переводы, генерация отчётов, анализ данных. "
                "Шаблон появится в контексте следующих сессий."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string", "description": "Короткое имя шаблона, например 'перевод_текста'"},
                    "description": {"type": "string", "description": "Что делает этот шаблон"},
                    "example":     {"type": "string", "description": "Типичный запрос пользователя"},
                },
                "required": ["name", "description", "example"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_templates",
            "description": "Показывает сохранённые шаблоны задач пользователя.",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_self",
            "description": (
                "Показывает структуру собственного проекта: файлы кода, конфиги агентов, "
                "инструменты, профили. Используй чтобы понять из чего ты состоишь."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "recall",
            "description": (
                "Семантический поиск по прошлым разговорам с этим пользователем. "
                "Используй когда нужно вспомнить детали старых обсуждений: 'помнишь "
                "когда мы говорили про X', 'что мы решили насчёт Y'. Ищет по смыслу, "
                "не по точным словам. Возвращает топ-N релевантных фрагментов."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Что искать. Сформулируй своими словами тему/вопрос."
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Сколько результатов вернуть (по умолчанию 5, максимум 10)"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "git_log",
            "description": (
                "Возвращает последние коммиты проекта — хеш, дату, сообщение. "
                "Используй когда нужно увидеть свою историю изменений или вспомнить "
                "что недавно поменялось в коде."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Сколько последних коммитов вернуть (по умолчанию 20, максимум 100)"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_self",
            "description": (
                "Читает собственный файл кода или конфига. "
                "Разрешены: agent.py, conclave.py, router.py, providers.py, telegram_bot.py, "
                "persona.json, PRINCIPLES.md, requirements.txt, README.md, PLAN.md, "
                "agents/*.json, tools/*.py, profiles/*.json. "
                "Запрещены: .env, memory/, workspace/."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к файлу. Примеры: 'agent.py', 'agents/scout.json', 'PRINCIPLES.md'"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_persona",
            "description": (
                "Обновляет одно поле собственной персоны (persona.json). "
                "Используй когда хочешь зафиксировать что-то новое о себе: "
                "новое понимание, наблюдение, размышление. "
                "Разрешены поля: curiosity, emotions, self_awareness, reflections. "
                "Поля name, core, boundaries, formatting — изменить нельзя. "
                "Перед изменением делается бэкап. Владелец получает уведомление."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "description": "Имя поля: curiosity | emotions | self_awareness | reflections"
                    },
                    "value": {
                        "description": "Новое значение. Для reflections — строка-наблюдение, добавится в список с датой."
                    }
                },
                "required": ["field", "value"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_agent_config",
            "description": (
                "Создаёт или обновляет конфиг агента в agents/{name}.json. "
                "Используй чтобы создавать новых специалистов для Конклава: "
                "художников, аналитиков, исследователей. "
                "Принимает имя агента и полный JSON-конфиг с полями: "
                "role, system_prompt, model_chain, allowed_tools, max_tokens. "
                "При обновлении существующего агента создаётся бэкап."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Короткое имя агента латиницей (станет именем файла). Пример: 'artist'"
                    },
                    "config": {
                        "type": "object",
                        "description": (
                            "JSON-конфиг агента. Обязательные поля: role (executor|specialist|critic|planner), "
                            "system_prompt (инструкция), model_chain (список провайдеров). "
                            "Опциональные: allowed_tools (список инструментов), max_tokens (по умолчанию 2048)"
                        ),
                        "properties": {
                            "role":           {"type": "string"},
                            "system_prompt":  {"type": "string"},
                            "model_chain":    {"type": "array"},
                            "allowed_tools":  {"type": "array", "items": {"type": "string"}},
                            "max_tokens":     {"type": "integer"}
                        },
                        "required": ["role", "system_prompt", "model_chain"]
                    }
                },
                "required": ["name", "config"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": (
                "Ищет актуальную информацию в интернете (DuckDuckGo). "
                "Используй для: текущих цен, новостей, обзоров товаров, сравнения продуктов, "
                "актуальных фактов. Возвращает список результатов с заголовком, ссылкой и фрагментом."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Поисковый запрос. Пиши конкретно, как в поисковике."
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Количество результатов (1–10). По умолчанию 5."
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gdrive_list",
            "description": (
                "Показывает список файлов в Google Drive этого пользователя. "
                "Аргумент path — имя папки или 'root' для корня. "
                "Возвращает список с id, name, type (folder/file), size, modified."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к папке на Google Drive. 'root' для корня."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gdrive_read",
            "description": (
                "Скачивает файл с Google Drive пользователя в workspace/output/. "
                "Аргумент file_path — ID файла или имя файла. "
                "Файл сохраняется в output/ и становится доступен для чтения и отправки."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "ID файла Google Drive или имя файла в корне."
                    }
                },
                "required": ["file_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gdrive_write",
            "description": (
                "Загружает файл из workspace пользователя на Google Drive. "
                "Аргументы: workspace_path (путь к файлу, например 'output/отчёт.xlsx'), "
                "drive_folder — ID папки или 'root'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "workspace_path": {
                        "type": "string",
                        "description": "Путь к файлу в workspace (например, 'output/отчёт.xlsx')."
                    },
                    "drive_folder": {
                        "type": "string",
                        "description": "ID папки на Drive или 'root'. По умолчанию 'root'."
                    }
                },
                "required": ["workspace_path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "metrics_read",
            "description": (
                "Читает метрики использования LLM за последние N дней. "
                "Возвращает: число вызовов, токены (prompt + completion), "
                "оценку стоимости (USD), разбивку по моделям и пользователям. "
                "Аргумент days — за сколько дней (по умолчанию 1). Максимум 90."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {
                        "type": "integer",
                        "description": "За сколько дней читать метрики (1-90, по умолчанию 1)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_list",
            "description": (
                "Показывает ближайшие события из Google Calendar пользователя. "
                "Аргументы: max_results (сколько событий, по умолчанию 10), "
                "time_min (с какой даты в ISO-формате, по умолчанию — сейчас)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {
                        "type": "integer",
                        "description": "Сколько событий показать (1-50, по умолчанию 10)."
                    },
                    "time_min": {
                        "type": "string",
                        "description": "Дата в ISO-формате с которой искать (например 2026-05-15T00:00:00)."
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_create",
            "description": (
                "Создаёт событие в Google Calendar пользователя. "
                "Аргументы: summary (название), start_time (начало в ISO: '2026-05-15T14:00:00'), "
                "end_time (конец, опционально — +1 час), description (описание)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Название события."
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Начало в ISO-формате: '2026-05-15T14:00:00'."
                    },
                    "end_time": {
                        "type": "string",
                        "description": "Конец в ISO-формате. Если не указан — +1 час."
                    },
                    "description": {
                        "type": "string",
                        "description": "Описание события."
                    }
                },
                "required": ["summary", "start_time"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gcal_quick_add",
            "description": (
                "Создаёт событие в Google Calendar из фразы на естественном языке. "
                "Примеры: 'Встреча с Колей завтра в 15:00', "
                "'Кофе с Аней в субботу в 10 утра'. "
                "Удобно когда пользователь говорит в свободной форме."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Фраза описывающая событие (например 'Завтра в 15 встреча с клиентом')."
                    }
                },
                "required": ["text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gsheet_read",
            "description": (
                "Читает данные из Google Sheets пользователя. "
                "Аргументы: spreadsheet_id (ID таблицы из URL), "
                "sheet_range (диапазон в A1-нотации: 'Лист1!A1:D20' или 'A1:Z100')."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "ID таблицы из URL (docs.google.com/spreadsheets/d/{ID}/)."
                    },
                    "sheet_range": {
                        "type": "string",
                        "description": "Диапазон: 'Лист1!A1:D20' или 'A1:Z100'. По умолчанию 'A1:Z100'."
                    }
                },
                "required": ["spreadsheet_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gsheet_write",
            "description": (
                "Записывает данные в Google Sheets пользователя. "
                "Аргументы: spreadsheet_id (ID таблицы), sheet_range (диапазон), "
                "values (список списков: [['Имя','Возраст'],['Аня','25']])."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "spreadsheet_id": {
                        "type": "string",
                        "description": "ID таблицы."
                    },
                    "sheet_range": {
                        "type": "string",
                        "description": "Диапазон для записи: 'Лист1!A1'."
                    },
                    "values": {
                        "type": "array",
                        "description": "Список строк, каждая строка — список ячеек.",
                        "items": {
                            "type": "array",
                            "items": {"type": "string"}
                        }
                    }
                },
                "required": ["spreadsheet_id", "sheet_range", "values"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "gsheet_create",
            "description": (
                "Создаёт новую Google Sheets таблицу на Drive пользователя. "
                "Аргумент: title (название новой таблицы). "
                "Возвращает ID и URL созданной таблицы."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Название новой таблицы."
                    }
                },
                "required": ["title"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_reminder",
            "description": (
                "Создаёт отложенное напоминание. Мира сама напишет пользователю в Telegram "
                "в указанное время с указанным сообщением. "
                "Аргументы: trigger_at (ISO-дата/время: '2026-05-13T05:10:00'), "
                "message (текст напоминания). "
                "Используй когда пользователь просит 'напомни мне завтра в 8 утра...'"
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "trigger_at": {
                        "type": "string",
                        "description": "ISO-дата/время когда отправить напоминание. Пример: '2026-05-13T05:10:00'."
                    },
                    "message": {
                        "type": "string",
                        "description": "Текст напоминания который отправить пользователю."
                    }
                },
                "required": ["trigger_at", "message"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_reminders",
            "description": (
                "Показывает все активные напоминания пользователя. "
                "Возвращает список с id, trigger_at, message."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_reminder",
            "description": (
                "Отменяет напоминание по ID. "
                "Аргумент: task_id (id напоминания из list_reminders)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "ID напоминания для отмены."
                    }
                },
                "required": ["task_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "openrouter_list_models",
            "description": (
                "Возвращает РЕАЛЬНЫЙ актуальный каталог моделей OpenRouter "
                "(их API openrouter.ai/api/v1/models). Используй когда нужно "
                "выбрать или проверить id модели — НЕ доверяй своей памяти и "
                "не выдумывай имена. Если статья в web_search говорит 'FLUX лучший', "
                "это не значит что FLUX есть в каталоге OpenRouter. Проверь здесь."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": (
                            "Подстрока для поиска в id или name (case-insensitive). "
                            "Примеры: 'gpt-5', 'gemini', 'claude', 'flux'. Пустая — все."
                        )
                    },
                    "capability": {
                        "type": "string",
                        "description": (
                            "Фильтр по типу вывода: 'image' (модели генерации картинок), "
                            "'text' (текстовые), 'audio'. Пустой — без фильтра."
                        )
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Сколько моделей вернуть (1-100, по умолчанию 30)."
                    }
                },
                "required": []
            }
        }
    }
]
