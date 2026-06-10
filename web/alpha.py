"""web/alpha.py — запуск агента (alpha) из веб-слоя.

Общая точка для WS-чата, шедул-задач и ритуалов.
"""

import os
import time
import logging

import providers as _providers
from router import classify
from conclave import Conclave
from agent import (
    Agent, Profile, SYSTEM_PROMPT, TOOL_SCHEMAS, execute_tool,
    WORKSPACE_DIR, load_user_profile,
)
from web.sessions import MAX_HISTORY, _is_approved, _load_session, _system_prompt_for

logger = logging.getLogger("MiraWeb")


def _invoke_alpha(user_id: str, prompt: str,
                  source: str = "user",
                  agent_override: str | None = None) -> tuple[str, list[dict]]:
    """Запускает alpha.run с prompt, возвращает (answer, attachments).

    source: "user" | "scheduled_task" | "ritual" — для логирования.
    agent_override: если задан — крутить на этом агенте (ритуалы с полем
        "agent", напр. self_review на coder/Opus), иначе alpha по статусу.
    Не сохраняет сессию — caller решает.
    """
    from tools import semantic_memory as _sm
    _exec = execute_tool

    is_appr = _is_approved(user_id)
    if is_appr:
        pd = load_user_profile(user_id) or {}
        profile = Profile("dev") if pd.get("status") == "owner" else Profile("default")
        agent_name = "alpha"
    else:
        profile = Profile("guest")
        agent_name = "alpha_guest"

    if agent_override:
        agent_name = agent_override

    sys_prompt = _system_prompt_for(user_id)
    try:
        alpha = Agent.from_config_file(agent_name, profile, user_id, sys_prompt)
    except FileNotFoundError:
        return "[конфиг агента не найден]", []

    msgs = _load_session(user_id)
    msgs.append({"role": "user", "content": prompt, "ts": time.time()})
    system = [m for m in msgs if m["role"] == "system"]
    the_rest = [m for m in msgs if m["role"] != "system"]
    msgs = system + the_rest[-MAX_HISTORY:]

    # Семантический augment
    augment = ""
    try:
        matches = _sm.search(user_id, prompt, top_k=5, max_distance=0.35)
        augment = _sm.format_for_prompt(matches)
    except Exception as e:
        logger.warning(f"semantic recall: {e}")

    llm_msgs = [{k: v for k, v in m.items() if k != "ts"} for m in msgs]
    if augment and llm_msgs and llm_msgs[0].get("role") == "system":
        llm_msgs[0] = {**llm_msgs[0], "content": llm_msgs[0]["content"] + "\n\n" + augment}

    # Снимок output/ до
    out_dir = os.path.join(WORKSPACE_DIR, user_id, "output")
    out_before: dict[str, float] = {}
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            fp = os.path.join(out_dir, f)
            if os.path.isfile(fp) and not f.startswith("."):
                out_before[f] = os.path.getmtime(fp)

    # Классификация + роутинг
    task_type = classify(prompt, alpha.model_chain if alpha else [])
    _EXECUTOR_FOR = {"search": "scout", "code": "coder", "complex": "coder", "image": "artist"}

    try:
        if task_type in _EXECUTOR_FOR and alpha:
            conclave = Conclave(
                system_prompt=SYSTEM_PROMPT, user_id=user_id,
                profile=profile, tool_schemas=TOOL_SCHEMAS, execute_tool_fn=_exec,
            )
            executor = _EXECUTOR_FOR[task_type]
            raw = conclave.run_with_qa(prompt, executor)
            sys_with_aug = SYSTEM_PROMPT + ("\n\n" + augment if augment else "")
            presentation = f"Специалисты выполнили задачу. Представь результат:\n\n{raw}"
            recent = [m for m in msgs if m.get("role") != "system"][-12:]
            alpha_msgs = [
                {"role": "system", "content": sys_with_aug},
                *recent,
                {"role": "assistant", "content": "[передала специалистам]"},
                {"role": "user", "content": presentation},
            ]
            answer = _providers.call(alpha.model_chain, alpha_msgs, temperature=0.7,
                                     user_id=user_id, agent_name=alpha.name).choices[0].message.content
        else:
            answer = alpha.run(llm_msgs)
    except Exception as e:
        logger.error(f"_invoke_alpha: {source} error: {e}")
        return f"Ошибка: {e}", []

    # Снимок output/ после
    attachments: list[dict] = []
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            fp = os.path.join(out_dir, f)
            if not os.path.isfile(fp) or f.startswith("."):
                continue
            mt = os.path.getmtime(fp)
            if f not in out_before or mt > out_before[f] + 0.5:
                attachments.append({"name": f, "dir": "output", "size": os.path.getsize(fp)})

    # Сливаем pending attachments (если есть)
    from tools.file_tools import pop_pending_attachments
    manual = pop_pending_attachments(user_id)
    merged = list({(a["name"], a["dir"]): a for a in (attachments + manual)}.values())

    logger.info(f"_invoke_alpha: {source} ok ({len(answer)} символов, {len(merged)} attachments)")
    return answer, merged
