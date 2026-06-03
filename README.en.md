<div align="center">

# 🌟 Mira

### A personal AI assistant that lives in Telegram, the browser, the desktop and your phone — at once

<sub>[🇷🇺 Русский](README.md) · 🇬🇧 English</sub>

[![Version](https://img.shields.io/badge/version-2.4-brightgreen?style=for-the-badge)](https://github.com/Glombert/Mira_BOT/releases)
[![Mobile](https://img.shields.io/badge/Mobile-Android_APK-FF8C42?style=for-the-badge&logo=android&logoColor=white)](https://github.com/Glombert/Mira_Mobile/releases/latest)
[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

<sub>**Models:** Claude · DeepSeek · Gemini · OpenRouter &nbsp;·&nbsp; **Integrations:** Telegram · Google Drive · Calendar · Sheets</sub>

<br/>

> *"What do I need to do tomorrow at 8 a.m.?" — ask in any interface; at 8 a.m. Mira pushes the answer to you herself.*

</div>

---

## What it is

Mira is **your own AI assistant**, reachable through whatever window is convenient: a Telegram bot, a phone app, the browser or the desktop. **Same conversation, same context** — everything stays in sync.

Unlike cloud chatbots, Mira:

- 🧠 **Remembers you** across sessions — your name, projects, habits, conversations from weeks ago
- 🔧 **Gets things done** — not just answers: reads your files, opens the calendar, reads Google Sheets, fetches from Drive
- ⏰ **Works in the background** — "tomorrow at 8:00 prepare the sales report" → at 8:00 a push arrives with the result
- 🤖 **Reviews and improves herself** — every two weeks she reviews her own code, hunts for vulnerabilities, parses logs for recurring errors, and watches for newer models
- 🔄 **Doesn't die on one provider** — Claude down → DeepSeek → Gemini, transparently
- 🛡 **Yours** — runs on your own VPS, no cloud subscriptions, the API keys are only yours

## Real examples

```
you:   "Hey, anything important today?"
Mira:  Checks your history, calendar, recent messages → gives a digest.

you:   [attach a PDF] "What's this?"
Mira:  Reads it, summarizes, and can build an Excel of the key data.

you:   "/task Friday 3pm check the team's task status and prepare a report"
Mira:  Friday 3pm — a push with the finished report.

you:   "Create a Google Sheet with May expenses"
Mira:  Sheet created and shared to your email.
```

## Architecture

<div align="center">

```
                  ┌─────────────────────────────────────┐
                  │      YOU — one voice, any window     │
                  └──────────────┬──────────────────────┘
       ┌──────────┬──────────────┼──────────────┐
       ▼          ▼              ▼              ▼
   📱 Mobile   💻 Web        🖥 Desktop      💬 Telegram
   (RN)       (Next.js)     (Tauri v2)      (bot)
       │          │              │              │
       └──────────┴──────┬───────┴──────────────┘
                         │ WebSocket / HTTP
                         ▼
              ┌──────────────────────────┐
              │      MIRA (Alpha)        │
              │  • dialogue, context     │
              │  • user memory           │
              │  • answers HERSELF +     │
              │    calls tools           │
              └────────────┬─────────────┘
                           │ background (rituals, scheduled tasks)
                           ▼
              ┌────────────────────────────┐
              │   AUTONOMY + CONCLAVE       │
              ├────────────────────────────┤
              │ Rituals (cron + LLM)       │
              │ Scheduled tasks            │
              │ Conclave pipeline:         │
              │  Coder → Editor → Critic   │
              └────────────────────────────┘
```

</div>

**One voice — Mira.** In chat she **answers herself** (`alpha.run` with tools: search, code, calendar, images). The Conclave specialist pipeline (Coder → Editor → Critic) runs in **background tasks and rituals**, not on every chat message.

## Under the hood

| Layer | Tech |
|---|---|
| **LLM stack** | Claude Sonnet 4.6 / Opus 4.8 (Anthropic) · DeepSeek V4 · Gemini · OpenRouter (failover chain) |
| **Backend** | Python 3.12 · FastAPI · WebSocket · python-telegram-bot · SQLite (WAL) · Fernet-encrypted memory |
| **Contract** | `web/ws_protocol.py` (pydantic) — single source of truth for WS/REST; a parity test against TypeScript catches drift |
| **Memory** | Structured summary · profiles · ChromaDB (semantic search) |
| **Clients** | React Native (mobile) · Next.js (web) · Tauri v2 (desktop) — monorepo with shared design tokens |
| **Push** | Firebase Cloud Messaging (FCM) |
| **Integrations** | Google Drive · Calendar · Sheets · rclone · DuckDuckGo Search · Claude Vision |
| **Security** | firejail-sandboxed Python (fail-closed) · per-user workspace · path-traversal protection · HMAC sessions |
| **Observability** | Sentry-compatible error capture (`SENTRY_DSN`) + secret redaction in logs |
| **Self-evolution** | `/evolve` — Mira edits her own code through layered validation (whitelist → syntax → smoke test → atomic rollback) |

## Monorepo layout

```
mira_agent/
├── agent.py, conclave.py, router.py, providers.py   ← core: agent, Conclave, failover
├── agent_tools.py                                   ← tool registry + execute_tool
├── telegram_bot.py                                  ← Telegram bot + ritual/task loops
├── web/                                             ← FastAPI + WebSocket
│   ├── app.py                                       ← WS handler, REST
│   ├── ws_protocol.py                               ← pydantic contract (source of truth)
│   └── routes/, deps.py, security.py
├── agents/*.json                                    ← agent configs (one class, different models)
│   └── rituals/*.json                               ← background jobs (cron + on_startup)
├── tools/                                           ← tools (Google, files, memory, logs, …)
├── clients/                                         ← npm workspaces (web/desktop)
│   ├── apps/web/ (Next.js), apps/desktop/ (Tauri v2)
│   └── packages/shared/ (shared TS types + design tokens)
├── mobile/                                          ← React Native (APK built in CI → Mira_Mobile)
├── memory/                                          ← runtime data (mira.db, chroma, overlay)
└── scripts/                                         ← deploy, backup, release, smoke
```

`clients/packages/shared/src/tokens.ts` is the single source of design tokens (palette, fonts, radii): both the web (Tailwind) and mobile (theme) consume it, so colors never diverge.

## Key features (v2.4)

- **Mira's voice** — no router gate: every message reaches Mira with the full *core* (character `persona.json` + rules `RULES.md`/`behavior.md` + the interlocutor's profile); she answers herself and calls tools herself.
- **Live rhythm** — long replies split into 2–3 messages (reaction / body / epilogue); code blocks and tables are never split.
- **Thought cloud** — before each `tool_call`, a human-readable action label (`web_search` → "searching the web…").
- **Self-improvement rituals** — biweekly: `self_review` (refactoring + security + ideas, on Opus), `log_audit` (recurring errors from logs), `agent_versions` (newer models), `weekly_summary` (usage/cost). Daily: `server_health`.
- **Owner tech channel** — a separate in-app channel for rituals, errors, access requests; a two-way "dev mode" with Mira (raw logs/stacks).
- **User-to-user messaging** — `find_user` / `send_to_user` with a two-step confirm (preview → confirm → deliver via TG + FCM).
- **Prompt cache split + persona overlay** — a `<<MIRA_DYNAMIC>>` marker caches the static core (Anthropic prompt caching); self-edited character fields live in a git-untracked overlay so prod `git pull` never conflicts.

[**→ Full release history**](https://github.com/Glombert/Mira_BOT/releases)

## Quick start

```bash
# Backend
git clone https://github.com/Glombert/Mira_BOT.git mira_agent && cd mira_agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
# fill .env (OpenRouter / Anthropic / DeepSeek keys, TELEGRAM_BOT_TOKEN, OWNER_TELEGRAM_ID)

export MIRA_ALLOW_UNSANDBOXED=1                       # dev only (no firejail → run_python blocked otherwise)
python telegram_bot.py                               # Telegram bot
uvicorn web.app:app --host 127.0.0.1 --port 8000     # web (FastAPI)

# Clients
cd clients && npm install && npm --workspace apps/web run dev   # Next.js
cd ../mobile && npm install                                     # React Native (APK is CI-only)
```

> ⚠️ Heavy native builds (gradle / `react-native run-android`) run **in CI only**, never locally.

**Tests:** `venv/bin/pytest -q` (backend, 407) · `cd clients/apps/web && npx vitest run` · `cd mobile && npx jest`

## Configuration (`.env`)

```env
API_OPENROUTER_KEY=sk-or-v1-...      API_OPENROUTER_URL=https://openrouter.ai/api/v1
API_DEEPSEEK_KEY=sk-...              API_DEEPSEEK_URL=https://api.deepseek.com/v1
API_ANTHROPIC_KEY=sk-ant-...
TELEGRAM_BOT_TOKEN=...               OWNER_TELEGRAM_ID=123456789
MEMORY_ENCRYPTION_KEY=...            # optional: Fernet memory encryption
SENTRY_DSN=...                       # optional: error capture
MIRA_MAX_CONCURRENT_LLM=6            # cap on concurrent LLM calls per process
```

## Deployment

Two systemd services (`mira-bot` + `mira-web`, templates in `scripts/`, with `MemoryMax`/`TasksMax` limits — important when a VPN shares the box), Nginx + Let's Encrypt via DuckDNS (`scripts/nginx.conf.example`), GitHub Actions auto-deploy on push, and a nightly backup that takes a **consistent SQLite snapshot**, syncs to Google Drive with `--backup-dir` versioning (point-in-time recovery), and GPG-encrypts `.env` off-site. Full disaster-recovery steps are in the [Russian README](README.md#disaster-recovery).

## Security

- **Guarded self-editing** — branch `mira-dev` → backup → `ast.parse()` → subprocess smoke test → `PRINCIPLES.md` check; any failure rolls back.
- **Access tiers** — `owner` / `regular` / `guest` (10 messages, no files, auto-removed after 3 days) / `rejected` / `blacklisted`; kid mode via `/kidmode`.
- **Prompt-injection** — user file contents wrapped in `BEGIN/END USER FILE` markers (data, not instructions).
- **Sandboxing** — `run_python` in firejail `--net=none`, fail-closed.
- **Thread-safe memory** — SQLite WAL + `ON CONFLICT DO UPDATE`, connection-per-thread.
- **Rate limiting** — sliding window (60 msg / 20 files per minute; owner exempt) + a concurrency semaphore protecting a small VPS.
- **Tests** — `pytest` (407) + a Python⟷TypeScript WS-contract parity test + client tests (vitest/jest), all CI-gated.

## License

MIT. Use it, fork it, break it, put it back together.

---

<div align="center">

*An agent that helps you think — not one that replaces your thinking.*

</div>
