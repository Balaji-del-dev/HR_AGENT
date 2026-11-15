"""Paused runs survive a restart: checkpoints live in PostgreSQL, readable by the runtime role."""

import io
from typing import TypedDict
from uuid import uuid4

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

pytestmark = pytest.mark.django_db


class State(TypedDict, total=False):
    draft: str
    decision: str


def _graph(saver: PostgresSaver):  # type: ignore[no-untyped-def]
    builder = StateGraph(State)
    builder.add_node("draft", lambda state: {"draft": "v1"})
    builder.add_node("review", lambda state: {"decision": interrupt({"type": "review", "draft": state["draft"]})})
    builder.add_edge(START, "draft")
    builder.add_edge("draft", "review")
    builder.add_edge("review", END)
    return builder.compile(checkpointer=saver)


def _conninfo(user: str, password: str) -> str:
    db = settings.DATABASES["default"]
    return (
        f"host={db['HOST']} port={db['PORT']} dbname={db['NAME']} user={user} password={password} "
        "options='-c search_path=langgraph'"
    )


def test_interrupted_run_resumes_from_a_new_saver_as_the_runtime_role() -> None:
    # Setup is an owner-role step (`make migrate`); the test suite runs as the app role, so switch back briefly.
    with connection.cursor() as cursor:
        cursor.execute("RESET ROLE")
    call_command("setup_agent_checkpoints", stdout=io.StringIO())
    with connection.cursor() as cursor:
        cursor.execute(f"SET ROLE {settings.DATABASE_APP_ROLE}")
    thread = {"configurable": {"thread_id": str(uuid4())}}
    app_role = _conninfo("hr_app", "hr_app_dev")

    with PostgresSaver.from_conn_string(app_role) as saver:
        events = list(_graph(saver).stream({}, thread, stream_mode="updates"))
        assert events[-1]["__interrupt__"][0].value == {"type": "review", "draft": "v1"}

    # A new process (a deploy, a crashed worker) picks the run up from PostgreSQL.
    with PostgresSaver.from_conn_string(app_role) as saver:
        graph = _graph(saver)
        assert graph.get_state(thread).next == ("review",)
        graph.invoke(Command(resume="approve"), thread)
        assert graph.get_state(thread).values == {"draft": "v1", "decision": "approve"}
        saver.delete_thread(thread["configurable"]["thread_id"])
        assert graph.get_state(thread).values == {}
