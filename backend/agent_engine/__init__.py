"""LangGraph agent engine. Runs inside Celery workers (agents queue).

Layout: state.py (graph state), schemas.py (structured outputs), graphs/
(supervisor and subgraphs), nodes/ (one module per agent), tools/ (registry
and tool groups), prompts/ (versioned Jinja2 templates), llm/ (model factory,
fallback, embeddings), guards/ (input and output checks), runtime.py
(checkpointer, run and resume, event streaming).
"""
