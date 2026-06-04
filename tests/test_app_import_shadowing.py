"""Регресс-гард на UnboundLocalError из-за теней импортов в web/app.py.

Боль из прода: внутри огромного WS-хендлера локальный
`from tools.rituals import load_rituals` сделал имя локальным для всей
функции, а использования выше по тексту (`load_rituals()` в текстовых
командах) упали с `cannot access local variable 'load_rituals'`.

Опасен именно случай «использование имени ДО его локального импорта» в одной
функции. Просто переимпорт (импорт раньше использования) безвреден и не
ловится — иначе пришлось бы запрещать ленивые импорты.
"""

import ast
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "web" / "app.py"


def _use_before_local_import(src: str):
    tree = ast.parse(src)

    def own_nodes(fn):
        nested = set()
        for n in ast.walk(fn):
            if n is not fn and isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for c in ast.walk(n):
                    nested.add(id(c))
        for n in ast.walk(fn):
            if id(n) not in nested:
                yield n

    bugs = []
    funcs = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    for fn in funcs:
        imp, load = {}, {}
        for n in own_nodes(fn):
            if isinstance(n, (ast.Import, ast.ImportFrom)) and n is not fn:
                for a in n.names:
                    nm = a.asname or a.name.split(".")[0]
                    imp[nm] = min(imp.get(nm, 1 << 30), n.lineno)
            elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                load[n.id] = min(load.get(n.id, 1 << 30), n.lineno)
        for nm, iln in imp.items():
            if nm in load and load[nm] < iln:
                bugs.append((fn.name, nm, load[nm], iln))
    return bugs


def test_no_use_before_local_import():
    bugs = _use_before_local_import(APP.read_text())
    assert not bugs, "Тень импорта → UnboundLocalError: " + "; ".join(
        f"{fn}: '{nm}' читается на стр.{u}, но локально импортится на стр.{i}"
        for fn, nm, u, i in bugs
    )


def test_detector_catches_known_pattern():
    buggy = (
        "from tools.rituals import load_rituals\n"
        "def h():\n"
        "    x = load_rituals()\n"
        "    from tools.rituals import load_rituals\n"
        "    return x\n"
    )
    assert _use_before_local_import(buggy) == [("h", "load_rituals", 3, 4)]
