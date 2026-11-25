# CLAUDE.md

## Goal

A website chatbot ("Coltek Assistant") for Coltek Technologies in Accra, Ghana. It covers three areas:
- **Coltek Technologies**: software, websites, mobile apps, AI solutions, school/church systems, corporate training.
- **Coltek Code Academy**: courses, enrolment, dates, fees.
- **OpenDoor**: the church management SaaS at open-door.site.

Stack: OpenAI Agents SDK (`openai-agents`), our own FastAPI chat API (Server-Sent Events), our own embeddable chat widget, and SQLModel on `DATABASE_URL`. **We do not use ChatKit**, neither its Python SDK nor its web component.

The course is split into parts: 1 setup, 2 first agent, 3 knowledge, 4 orchestration, 5 guardrails, 6 backend server, 7 website embed, 8 deployment, 9 testing and monitoring. Parts 1–5 live in `notebooks/`, and production code goes in `chatbot/`, `server/` and `embed/`.

## Architecture

```
website page
  └─ embed/ widget (our own, Shadow DOM)          POST /api/threads, GET /api/threads/{id}/messages,
        │  fetch + credentials (visitor cookie)    POST /api/chat → text/event-stream
        ▼
  server/ FastAPI chat API                         cookie, CORS, validation, rate limit, SSE,
        │  imports chatbot/                        threads/messages storage, logging
        ▼
  chatbot/ agents, prompts, tools, guardrails, db  OpenAI Agents SDK (Runner.run / run_streamed)
```

- **The import rule:** `chatbot/` must **never** import from `server/` or `embed/`. `server/` imports from `chatbot/`, never the other way round.
- **`chatbot/`** holds the agents, prompts, tools, guardrails and database models. It has no web code. These stay as they are unless the user asks.
- **`server/`** wraps `chatbot/` for the web.
- **`embed/`** is the browser widget. It only talks to `server/` over HTTP.
- **The other folders:**
  - `knowledge/` holds the markdown files uploaded to the OpenAI vector store.
  - `scripts/` holds the one-off scripts (knowledge upload, course seeding).
  - `deploy/` holds Docker, Nginx and systemd.
  - `tests/` holds the pytest suite.
- **`chatbot/agents/` is a package.** It doesn't conflict with the SDK only because the **project root** is on `sys.path`, never `chatbot/`. `import agents` must always resolve to the Agents SDK.

## Configuration

- `chatbot/config.py` uses pydantic-settings to read `<repo>/.env` into `settings`. The fields are:
  - `openai_api_key`
  - `openai_model` (from `OPENAI_MODEL`, or the old `MODEL`)
  - `guardrail_model`
  - `vector_store_id`
  - `database_url`
  - `allowed_origins` (plus `allowed_origins_list`)
  - `trusted_proxy_ips`
  - `session_history_limit`
  - `trace_include_sensitive_data`
  - `rate_limit_per_hour`
  - `app_env` (plus `is_production`)
  - the `SMTP_*` and `NOTIFY_EMAIL_TO` settings
- The module also exports `MODEL`, `GUARDRAIL_MODEL` and `VECTOR_STORE_ID`. It copies the key into `os.environ["OPENAI_API_KEY"]` if it isn't already there, because the OpenAI client reads it from the environment.
- Guardrail agents use the cheap `GUARDRAIL_MODEL`, which defaults to `gpt-5.4-nano`. `gpt-4.1-nano` has been retired and returns 404. `gpt-5.4-nano` is a *reasoning* model, so it may add noticeable delay.
- Notebooks run from `notebooks/`, so they call `sys.path.insert(0, os.path.abspath(".."))` and refer to the knowledge folder as `../knowledge`.
- **Notebooks never use the real database.** Notebooks 04 and 05 call `notebooks.notebook_db.use_test_database()` before importing `chatbot`. That sets `DATABASE_URL` to `notebooks/notebooks_test.sqlite3` (git-ignored) and adds the fake courses from `tests/fixtures.py`. It also provides `all_leads()`, `all_demo_requests()`, `all_courses()` and `clear_leads_and_demos()`.

## Agent design (notebook 04 → `chatbot/agents/`)

Where the code is:
- `sales.py` has `services_agent`, `academy.py` has `academy_agent`, and `support.py` has `opendoor_agent`.
- `common.py` has `file_search_for(*domains)`.
- `triage.py` has `triage_agent` and wires up the handoffs. It also defines:
  - `get_starting_agent(name)`: with no name it returns triage. It accepts a short name or an agent's full name, and falls back to triage for an unknown one.
  - `department_for(agent_name)` and `DEPARTMENTS`.
- The prompts are built in `chatbot/prompts.py`: `TRIAGE_INSTRUCTIONS`, `SERVICES_INSTRUCTIONS`, `ACADEMY_INSTRUCTIONS` and `OPENDOOR_INSTRUCTIONS`.
- `general.py` and `main_agent.py` (the 4a manager) are unused stubs.

The production structure is handoffs:
- **`triage_agent`**, named "Coltek Assistant":
  - Its instructions are `RECOMMENDED_PROMPT_PREFIX` + identity + `STABLE_FACTS` + `NEVER_RULES` + `TONE` + `TRIAGE_ROUTING`.
  - It has no file search.
  - It answers general company questions (location, contacts, who we are) itself, and hands off everything else.
  - `handoffs=[services_agent, academy_agent, opendoor_agent]`.
- **The specialists**:
  - Each one's instructions come from `build_specialist_instructions(ROLE)`: prefix + `STABLE_FACTS` + `KNOWLEDGE_RULES` + `NEVER_RULES` + `TONE` + role + `HANDBACK_LINE`.
  - Each has `handoffs=[triage_agent]`, set after triage is created.

| Agent `name` | Department | File search domains | Tools |
|---|---|---|---|
| `Coltek Assistant` (triage) | general | none | none |
| `Services and Sales Specialist` | services | `services`, `company` | `save_lead` |
| `Code Academy Advisor` | academy | `academy`, `company` | `check_course_intake`, `save_lead` |
| `OpenDoor Specialist` | opendoor | `opendoor`, `company` | `request_opendoor_demo` |

- **Domain-filtered search.** `FileSearchTool(vector_store_ids=[VECTOR_STORE_ID], max_num_results=5, include_search_results=True, filters={"type": "or", "filters": [{"type": "eq", "key": "domain", "value": d}, ...]})`.
- **Domain labels**, set at upload by `scripts/upload_knowledge.py: get_domain()`:

  | Files | `domain` |
  |---|---|
  | services.md, portfolio.md | `services` |
  | academy_courses.md | `academy` |
  | opendoor_product.md | `opendoor` |
  | company.md, faqs.md, contact_and_socials.md | `company` |

  The labels must match the filters exactly.
- **Agent names must not contain `&`.** The handoff tool name is built from the agent name.
- **Multi-turn:** every turn continues with the agent that replied last (saved as the thread's `last_agent`), with the conversation history. Don't restart from triage.
- **Prompts** are joined with `"\n\n".join([...])`. Don't use `{PLACEHOLDER}` templates; notebook 03 had placeholders that were never filled in.

## Guardrails (notebook 05 → `chatbot/guardrails.py`)

The agents in `chatbot/agents/` already have `INPUT_GUARDRAILS` and `OUTPUT_GUARDRAILS` attached. The offline tests are in `tests/test_guardrails_offline.py`, and they make no API calls.

**Input guardrails.** Both use `@input_guardrail(run_in_parallel=False)`, so a blocked message never reaches the agent or its tools.
1. **`sensitive_data_guardrail`**, regex with no LLM:
   - Looks for card-like digit runs of 13–19 digits, "PIN/password/passcode is …", and OTP codes.
   - Checks only the latest user message.
   - Trips with `{"reason": "sensitive_data", ...}`.
   - Ghana phone numbers must pass, because `save_lead` needs them.
2. **`classifier_guardrail`**: runs `input_classifier` on `GUARDRAIL_MODEL` and trips on `is_blocked`. Its `output_type=InputCheck` has:
   - `category`: allowed / off_topic / abusive / injection
   - `is_blocked`, `reason`, `language`

Input guardrails only run on the **first** agent in a run. From turn 2 the run starts at a specialist (`last_agent`), so all four agents have them.

**Output guardrails**, on **all four agents**: triage and every specialist. Any of them can give the final answer.
1. **`price_date_guardrail`**, regex with no LLM. It reads the `courses` table on every check:
   - Any GHS/cedi amount that isn't a course fee or payment-option amount trips `unapproved_price`.
   - Any specific date that isn't a course start date, an application deadline, or 5 Nov 2025 trips `unapproved_date`.
2. **`checker_guardrail`**: runs `output_checker` and trips on `is_unsafe`. Its `output_type=OutputCheck` has:
   - `is_unsafe`
   - `issue`: none / promise / legal_advice / leaked_instructions / wrong_company / asked_for_secret
   - `explanation`

**Fallbacks:**
- `FALLBACKS` maps every reason or issue to the message the visitor sees: `off_topic`, `abusive`, `injection`, `sensitive_data`, `unapproved_price`, `unapproved_date`, `promise`, `legal_advice`, `leaked_instructions`, `wrong_company`, `asked_for_secret`. Anything without its own entry gets `DEFAULT_FALLBACK`.
- `get_reason(output_info)` reads the reason from any guardrail's output.
- `safe_run(agent, input, **run_kwargs)` catches both tripwire exceptions and returns `{"reply", "blocked", "reason", "guardrail", "result"}`.
- The chat API catches the tripwires itself, because it streams. It uses the same `FALLBACKS` and `get_reason`, saves `guardrail_flag` on the thread, and logs the reason.

## Server (`server/`): our chat API

**Endpoints** (`main.py`):
- `POST /api/threads` `{page}` → `{thread_id}`
- `GET /api/threads/{id}/messages`, which returns 404 if the thread isn't this visitor's
- `POST /api/chat` `{thread_id, message, page}` → `text/event-stream`
- `GET /health`

**`main.py` details:**
- **The visitor cookie `coltek_vid`:** httpOnly, Secure + SameSite=None in production, Lax in development.
- **CORS** comes from `ALLOWED_ORIGINS`, with credentials allowed and the headers `Content-Type` and `X-Coltek-Page`.
- **Proxy IPs:** `X-Forwarded-For` is only trusted from `TRUSTED_PROXY_IPS`, and then only its last entry.
- **Startup** raises if `OPENAI_API_KEY` or `VECTOR_STORE_ID` is missing, then creates the tables.
- **Messages:** HTML tags are stripped, then a message must be 1–2000 characters (otherwise 422).
- **Rate limit** (`rate_limit.py`): in memory, `RATE_LIMIT_PER_HOUR` per visitor and 5× that per IP (429 with `Retry-After`).
- **One reply at a time per thread** (409).
- **Streaming headers:** `Cache-Control: no-cache` and `X-Accel-Buffering: no`.

**`chat_service.py`:**
- **Starting agent:** the thread's `last_agent`, otherwise an "academy" page → Academy, `open-door.site` → OpenDoor, otherwise triage.
- **Academy is run with `Runner.run` (not streamed),** so the output guardrails finish before anything is shown. Everything else uses `Runner.run_streamed`.
- **The SSE events** (JSON in `data`):
  - `start {thread_id}`
  - `agent {name}`, on a handoff
  - `status {text}`, when a tool starts. The text is **only ever one of `STATUS_TEXTS`**: "Checking course details...", "Saving your details...", "Booking your demo...", and the fallback "One moment..." for any tool not in `TOOL_STATUS`, such as file search. Never a tool name.
  - `delta {text}`
  - `reset {}`, only when an output guardrail blocks a reply that was already partly streamed; the widget must clear that bubble
  - `done {message_id, agent}`
  - `error {text}`
  - `: keep-alive` comments every 15 s
- **After a normal run** it saves the user and assistant messages and the thread's `last_agent` and `department`.
- **Logging:** one JSON `chat_run` line per run, containing ids, agent names and tool *names* only.
- **Tests:** they set `chat_service.MODEL_OVERRIDE` to `tests/fake_model.py: FakeModel`. Production leaves it `None`.
- **Safe retries:** every `POST /api/chat` carries a `client_message_id` (a uuid, required), stored on the user's `chat_messages` row.
  - If the same id arrives again for the same thread and a reply was saved, `main.py` replays the saved reply (`replay_turn`: `start`, `delta`, `done`) without running the agent and without counting it against the rate limit. So no duplicate messages or leads.
  - If the id is known but has no reply yet, the API answers 409.
  - A failed turn saves nothing, so retrying it runs normally.
  - `models.create_tables()` adds the column to older tables.

**Guardrail trips** (verified with tests):
- **The problem:** the SDK has already saved the turn's items to the session when a tripwire fires. `chat_service` counts the session items before the run and calls `sessions.rewind_to(count)` afterwards.
- **Input tripwire:**
  - Session: removes the blocked message, then adds `"[message blocked: <reason>]"` and the fallback.
  - `chat_messages`: stores that same placeholder, never the typed text.
- **Output tripwire:**
  - Session: removes *every* item of the turn (the message, tool calls, results, handoffs, the bad reply), then adds the visitor's original (safe) message and the fallback.
  - `chat_messages`: stores the message and the fallback (`blocked_reason` set).
- **Both:** set the thread's `guardrail_flag`.
- **Errors and cancelled streams** rewind the session too.

**Storage** (one `DATABASE_URL` for everything):
- `models.py`: `chat_threads` and `chat_messages` (what the visitor sees). These are SQLModel tables on the sync engine.
- `sessions.py`: the Agents SDK `SQLAlchemySession`, one per thread (`session_id` = thread id), on an **async** engine.
  - `DATABASE_URL` is converted automatically: `sqlite:///…` becomes `sqlite+aiosqlite:///<abs path>`, and `postgresql://…` becomes `postgresql+asyncpg://…`.
  - `SessionSettings(limit=SESSION_HISTORY_LIMIT)` (default 40) controls what the model sees.
  - Tables: `agent_sessions` and `agent_messages`.

**Run context:** `context.py: AgentRunContext(visitor_id, source_page, thread_id)` is passed as `context=`. The tools read `visitor_id` and `source_page` by attribute name through `chatbot/context.py: context_values()`. The IP is never passed.

## Widget (`embed/`)

- **What it is:** a TypeScript Web Component `<coltek-chat>` in an **open Shadow DOM**, built by Vite into ONE classic IIFE script, `embed/dist/coltek-chat.js`. It has no runtime dependencies and no ChatKit.
- **Build:** `cd embed && npm run build` runs `tsc`, then `vite build`, then `scripts/check-size.mjs`, which **fails over 25 KB gzipped**.
- **The panel is built only on first open,** but its code ships in the same file (option A, chosen for WordPress compatibility).
- **Config** comes from `data-*` on the script tag, or `window.ColtekChatConfig` (`data-*` wins). See `embed/README.md`. Brand placeholders until the real values arrive: primary `#0B2545`, accent `#13C4A3`, text `#1B1B1B`, surface `#FFFFFF`.
- **CSP rules:**
  - no inline handlers, no `eval`, no `innerHTML` (icons and Markdown are built with DOM APIs)
  - CSS only inside the shadow root, as a constructable stylesheet, with `<style>` only as a fallback
  - CSS variables set through CSSOM
- **The UI ignores the `agent` event,** which is logged to the console only when `debug` is on. Visitors see one assistant.
- **Send queue:** visitors can keep sending while a reply streams.
  - New messages show at once ("Waiting to send…") and wait in a queue in `panel.ts`, at most `MAX_QUEUED = 3`.
  - They're sent one after another, each reply placed directly under its message. The server allows one reply per thread at a time (409 otherwise), which keeps the agent's session history in order.
  - A failed message pauses the queue until Retry; when the failure was because the visitor was offline, it resumes automatically once they're back online.
  - A full queue keeps the text in the box and shows a notice.
- **What it sends:** host + path as the page (never the query string), `credentials: "include"`, and a new `client_message_id` per message; Retry reuses it.
- **Phones:**
  - under 640px it opens full screen, locks page scroll and sizes itself to `visualViewport` (the on-screen keyboard)
  - safe-area insets (needs `viewport-fit=cover` on the site)
  - the input font is 16px, so iOS doesn't zoom
- **Testing:** with headless Chrome against a fake-model API, with no OpenAI calls. Screenshots are in `embed/screenshots/`.

## Personal data: logs, traces, backups

- ⚠️ **These tables contain personal data:**
  - `agent_messages` holds every item the model saw, including tool calls **with their arguments** (the names and phone numbers passed to `save_lead` and `request_opendoor_demo`), as JSON.
  - `chat_messages` holds what visitors typed.
  - `leads` and `demo_requests` hold contact details.
- **Include all of them in backups, deletion requests and retention clean-up.** To delete a visitor's data, delete their `chat_threads` rows, those threads' `chat_messages`, the `agent_sessions` and `agent_messages` rows whose `session_id` is one of their thread ids, and their `leads` and `demo_requests` (by `visitor_id` or phone).
- **Logs never contain message text, tool arguments, names or phone numbers.**
  - `chat_run` logs ids, agent names and tool names only.
  - `notify.py` doesn't log the email subject.
  - Run errors log only the exception *type*. The full traceback is logged only when `TRACE_INCLUDE_SENSITIVE_DATA=true`.
  - `tests/test_api.py::test_logs_contain_no_message_text_or_tool_arguments` guards this.
- **Traces:**
  - `TRACE_INCLUDE_SENSITIVE_DATA` defaults to **false**, so spans are still uploaded but without model inputs and outputs or tool arguments and results. `chatbot/config.py` exports it as `OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA`, which the SDK reads for every `RunConfig`, including the guardrails' inner runs.
  - Verified: with it true, a `save_lead` trace contained the visitor's name and phone; with it false, neither.
  - Switch it on only locally while debugging.
- **Tests disable tracing completely** (`OPENAI_AGENTS_DISABLE_TRACING=1` and `set_tracing_disabled(True)` in `tests/conftest.py`).

## Tools and data (`chatbot/tools.py`, `chatbot/db.py`)

- **The database** is in `chatbot/db.py`. It uses SQLModel and `DATABASE_URL`, and has the tables `courses`, `leads` and `demo_requests`.
  - A relative SQLite path is resolved against the project root, so the notebooks, scripts and server all share one file.
  - The tables are created on first use.
  - `scripts/seed_courses.py` upserts the courses. Its fees and dates are `None` until the user fills them in.
- **The tools:** `check_course_intake(slug)`, `save_lead(...)` and `request_opendoor_demo(...)` are `@function_tool`s that read and write the database.
  - Each one's first parameter is `ctx: RunContextWrapper[Any]`, which the SDK hides from the model.
  - `visitor_id` and `source_page` come from the run context, never from the model.
- **Phone numbers** are normalised to E.164: `0XXXXXXXXX` and `233XXXXXXXXX` both become `+233XXXXXXXXX`.
- **References** are made from the row ID, like `CT-L-000001` (leads) and `CT-D-000001` (demo requests).
- **Errors:** missing consent returns `CONSENT_REQUIRED`, and duplicates return `DUPLICATE_LEAD` (same phone and interest) or `DUPLICATE_DEMO_REQUEST` (same phone and church name, ignoring case).
- **Demo consent:** `request_opendoor_demo` has no consent parameter, so the call itself is recorded as consent. The OpenDoor instructions only allow the call after a clear yes.
- **Team email:** `chatbot/notify.py: notify_team(subject, body)` emails the team after every new lead or demo request, using the `SMTP_*` and `NOTIFY_EMAIL_TO` settings. It never raises. If SMTP isn't configured, it logs a warning.
- **Tests:**
  - `tests/conftest.py` sets `DATABASE_URL` to a temporary file before anything is imported, and gives each test a fresh SQLite database filled from `tests/fixtures.py` (the old fake data).
  - Tests must never touch the real database or send email.
  - Live tests (marker `live`) are skipped by default.

## Rules for Claude

- **Verify every Agents SDK API against the installed source before using it.** Don't guess signatures, and don't rely on memory. The source is in `venv/lib/python3.12/site-packages/agents/` (openai-agents 0.25.0). For example, use `inspect.signature`, or read the module.
- **Keep tool names, parameters and docstrings unchanged unless the user approves.** The prompts and `handoff_description`s refer to them by name.
- **Never hard-code secrets.** Keys and IDs come from `.env` via `chatbot/config.py`. `.env` is gitignored, and `.env.example` holds placeholders only.
- **Never put real lead data in tests.** Use obviously fake names and numbers.
- **Keep notebook code beginner-friendly**: plain loops, comments on each step, no compact tricks. The user is learning.
- **Don't run anything that calls the OpenAI API (live tests, notebooks, the server) without asking first.** It costs tokens.

## Commands

```bash
source venv/bin/activate
make test                                           # offline tests only (default; pytest.ini adds -m "not live")
make test-live                                      # live conversations, tests marked "live": COSTS API calls; ask first
make test-smoke                                     # one real question (live marker)
python scripts/seed_courses.py                      # upsert the courses (fill in the TODOs first)
python scripts/upload_knowledge.py                  # new vector store from knowledge/*.md, prints the ID
python scripts/upload_knowledge.py --list           # files + domain labels in the store from .env
python scripts/upload_knowledge.py --replace faqs.md
uvicorn server.main:app --reload --port 8000        # chat API (uses the OpenAI key for every chat message)
cd embed && npm install && npm run build            # widget → embed/dist/coltek-chat.js (+ 25 KB gzip check)
cd embed && python3 -m http.server 5500             # demo at http://localhost:5500/demo.html (API on :8000)
```
