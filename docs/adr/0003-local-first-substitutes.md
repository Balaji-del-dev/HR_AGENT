# ADR 0003: Local-first substitutes for external services

**Status:** Accepted (2026-11-14)

## Context

The plan names several external services: Keycloak, OPA, ClamAV, LLM Guard, MinIO/S3, pgvector, DeepEval and Langfuse. The project runs on one machine with local PostgreSQL 16 and Redis, without Docker, and with tight memory. Every feature still has to work and be tested end to end.

## Decision

Each external service sits behind a small interface with a local implementation. The production service plugs in through configuration, without code changes in the services or agents.

| Plan | Local implementation | Production switch |
|---|---|---|
| OPA | `policies/engine.py`: the same input document (`action`, `subject`, `resource`), evaluated in Python; unknown actions are denied | Set `OPA_URL`; the engine posts the same input to `/v1/data/hr/decision` and denies if OPA is unreachable |
| Keycloak / OIDC | Django session sign-in with django-axes lockout | Add mozilla-django-oidc as an authentication backend; `User.oidc_subject` is already there |
| ClamAV | Built-in rules (EICAR, PDF JavaScript, launch actions and embedded files, macro DOCX) | Set `CLAMAV_SOCKET`; files are streamed to clamd (INSTREAM) as well |
| LLM Guard | Pattern scanner (`document_ai/injection.py`) for resumes and user input; flagged lines stay visible to people but are marked | Add a model-based scanner behind `scan_for_injection` |
| S3 / MinIO | `LocalObjectStorage`, with the same buckets and keys and short-lived signed links bound to the user | An S3 implementation of the four-method `ObjectStorage` protocol |
| pgvector | Embeddings stored as `float8[]`; cosine is computed in Python per candidate, plus a lexical boost | Install `postgresql-16-pgvector`; `VECTOR_BACKEND=auto` switches to `embedding::vector` in SQL |
| An LLM provider | `offline` heuristics over the same masked prompt data (development default); `ollama` locally; `anthropic` for Claude | Set `LLM_PROVIDER=anthropic` |
| DeepEval | `evals/`: golden sets for extraction F1, matching accuracy, grounding, counterfactual fairness and red-team recall, stored as `EvalResult` rows, with `run_evals` as the gate | Add DeepEval metrics as further suites |
| Langfuse | Enabled when `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are set; the trace id is the run id | Same |
| react-pdf viewer | Text viewer over stored spans, page by page, with evidence highlighted; the original file is one signed download away | Optional |

## Consequences

- All tests run offline and deterministically (`LLM_PROVIDER=fake`, which scripts the offline model).
- The offline model is not an LLM. It shows the whole platform working, and it is the CI floor for the eval gate. Real quality has to be measured with `LLM_PROVIDER=ollama` or `anthropic` and `make evals`.
- Parallel graph branches only call the model. Database work stays on the graph's main thread, because Django connections are per thread. The Recruiter Assistant's `create_agent` tool calls are passed back to that thread by `agent_engine/bridge.py`.
