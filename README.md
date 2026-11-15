# HR Recruiter Agent Platform

A Django + React platform where LangGraph agents do the recruiting groundwork and people make every hire, reject and offer decision.

- **Agents recommend, people decide.** Any action that affects a candidate (an email, a stage change, an offer, an interview time) pauses the agent run at a LangGraph interrupt until the named person approves it.
- **Code enforces permissions, not the model.** Every agent tool goes through the policy engine with the caller's identity taken from server-side context, never from the model's output.
- **Evidence instead of scores.** Matching produces a criteria matrix in which every claim cites a resume span. There is no overall score.
- **Protected attributes stay out.** Names, contact details, gender markers and lines such as a date of birth are masked or withheld before any prompt. A counterfactual test in the eval gate checks this.

## Quick start (local Postgres and Redis, no Docker)

```bash
make db-setup      # once, asks for sudo: creates roles hr_owner + hr_app and database hr_platform
cd backend && uv sync && cd ..
make migrate       # migrations + LangGraph checkpoint schema, as hr_owner
make seed          # demo data; every user's password is demo-pass-2026
make seed-users    # or: tenants and users only (several per role), no hiring data
make reset-users   # delete all hiring data and keep only tenants, users and roles
make seed-candidates  # 100 candidate profiles from generated resumes (needs `make worker` running)
make fe-install
```

Run the platform (three terminals):

```bash
make run           # API + WebSockets at http://127.0.0.1:8050 (docs at /api/docs/)
make worker        # Celery: documents, agents, integrations, notifications queues
make fe-dev        # the app at http://127.0.0.1:5180
```

Open **http://127.0.0.1:5180** and sign in as `acme_recruiter`.

| Demo user | Role | Try |
|---|---|---|
| `acme_recruiter` | Recruiter | Candidate review, shortlist approval, JD studio, assistant |
| `acme_hr_admin`, `acme_hr_lead` | HR admin | Approve requisitions and offers (step 1); Admin page |
| `acme_manager` | Hiring manager | Own requisitions; candidate contact details are hidden |
| `acme_interviewer` | Interviewer | Only their interviews; scorecards |
| `acme_finance` | Finance approver | Offer approval (step 2) |
| `acme_auditor` | Auditor | Read-only audit log and analytics |
| `globex_*` | Same roles in a second tenant | Cannot see any Acme data |

## Choosing the model

Agents use the offline model unless you set `LLM_PROVIDER`:

| `LLM_PROVIDER` | What runs | When to use it |
|---|---|---|
| `offline` (dev default) | Deterministic heuristics that read the same masked prompt data | Demos, tests and machines without a model; no network, no RAM cost |
| `ollama` | A local model through Ollama (`qwen2.5:1.5b` by default; set `LLM_MODEL`) | Real LLM behaviour on your machine; needs about 1.5 GB of free RAM |
| `anthropic` | Claude (`claude-opus-5-5`) through langchain-anthropic; set `ANTHROPIC_API_KEY` | Production quality |

Embeddings work the same way: `EMBEDDING_PROVIDER=hash` (offline, dev default) or `ollama` with `all-minilm`. Structured output always uses JSON-schema mode; code validates every answer again before anything is stored.

## What is built

**Backend apps** (`backend/apps/`, each split into `api/`, `services.py`, `selectors.py`, `policies.py` where needed, `tasks.py`):

| App | Owns |
|---|---|
| core | Tenant, `TenantScopedModel`, tenancy, Row-Level Security migration op, request ids, realtime publishing |
| accounts | Users, per-tenant roles, session sign-in, member lookups |
| requisitions | Requisitions, comp bands, HR approval |
| jobs | Versioned JDs, requirements, JD templates, inclusive-language check |
| candidates | Candidates, consent per purpose, extracted facts with evidence, correction queue, erasure |
| documents | Upload links, quarantine, the resume pipeline, spans, chunks, evidence search |
| applications | Pipeline stages; every change has a person and a reason |
| matching | Criteria matrices (AI) and recruiter decisions (people), kept apart |
| interviews | Interviews, panels, proposed slots, scorecards |
| offers | Offers inside the band, HR then finance approval |
| communications | Email templates, drafts, idempotent sending |
| approvals | One approval flow for every gated draft |
| agents | Agent runs, steps, tool calls, prompt versions, eval results, WebSocket consumers |
| integrations | CSV import, signed ATS webhooks, built-in calendar |
| analytics | Whitelisted read-only reports |
| governance | Append-only audit log, data access log, retention, deletion requests, incidents |

**Agent engine** (`backend/agent_engine/`): a supervisor graph routes each run to one of 12 agents (requisition review, JD generation, sourcing, resume parsing, matching with validation, communication, scheduling, feedback summary, offer, recruiter assistant, analytics, compliance). Matching fans out one branch per candidate with `Send`. Runs pause at `interrupt()`, checkpoints live in PostgreSQL (schema `langgraph`), and a decision resumes the graph with `Command(resume=...)`. There are 28 tools, and each one is policy-checked, tenant-scoped and logged. Every run has tool-call and token budgets.

**Document AI** (`backend/document_ai/`): true file-type check, malware rules (EICAR, PDF active content, optional clamd), PyMuPDF extraction with hidden-text stripping, OCR fallback (Tesseract), invisible-Unicode removal, prompt-injection flags, span ids (`doc_<id>:p<page>:<start>-<end>`), and masking (Presidio plus known identity plus patterns).

**Frontend** (`frontend/`): React 19.3, MUI, TanStack Query with an orval-generated typed client, React Router, Zustand, React Hook Form with Zod, Recharts and i18next. Pages: dashboard, requisitions, JD studio, pipeline board, candidate review (criteria matrix beside the resume, with highlighted evidence and a blind-review mode), candidates, approvals inbox (JD, email, offer, schedule, shortlist and requisition editors), interviews and scorecards, offers, recruiter assistant, analytics, admin and agent run detail. Live run progress uses WebSockets with one-time tickets and falls back to polling.

The UI kit (`frontend/src/shared/ui/kit/`) covers:
- KPI cards, a data grid (search, sort, pagination), loading skeletons, and empty, error, success and offline states.
- Status badges with icons, so status is never shown by color alone.
- Breadcrumbs, lifecycle steppers, timelines and activity feeds.
- Avatars and avatar groups, confirmation dialogs, a drag-and-drop file dropzone, and copy buttons.

The shell adds a collapsible sidebar, a Ctrl+K command palette, a notification center, a user menu with a profile card, and light and dark modes. The React admin page lives at `/settings`, because `/admin` is Django's admin site.

## Commands

```bash
make test          # backend tests (run as hr_app, so Row-Level Security applies)
make evals         # LLM eval gate: extraction F1, matching accuracy, fairness, red team
make lint          # ruff + strict mypy
make api           # regenerate the OpenAPI schema and the typed React client
make fe-test       # Vitest component tests
make check         # everything CI runs
make beat          # scheduled jobs: retention purge, ATS sync, nightly evals, stuck runs
make help
```

## How tenant isolation works

Two fences, and each one holds on its own:

1. **Application.** Selectors filter by the caller's tenant and visibility.
2. **Database.** Every tenant-owned table has a Row-Level Security policy on `app.tenant_id`. The app connects as `hr_app`, which neither owns the tables nor has BYPASSRLS. The audit tables are append-only for that role.

A request activates its tenant right after authentication. A Celery task or agent run activates it per transaction. More detail is in [docs/adr/0001](docs/adr/0001-tenant-isolation-with-row-level-security.md).

To add a tenant-owned model, subclass `TenantScopedModel`, run `make makemigrations`, and add `EnableRowLevelSecurity("<model>")` to the migration. `test_every_tenant_table_has_rls` fails if you skip that last step.

## Decisions and deviations from the plan

- [ADR 0001](docs/adr/0001-tenant-isolation-with-row-level-security.md): Row-Level Security design.
- [ADR 0002](docs/adr/0002-object-permissions-without-django-guardian.md): assignment tables instead of django-guardian.
- [ADR 0003](docs/adr/0003-local-first-substitutes.md): the local-first substitutes (built-in policy engine with an OPA adapter, offline model, local object storage, optional pgvector, session sign-in in development) and what production adds.
# HR_AGENT
