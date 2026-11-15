"""Policy decision point: who may run which agent, call which tool, and decide which approval.

Services and the agent tool registry call :func:`policies.engine.decide`. The
built-in rules answer locally; set OPA_URL to send the same input document to
an Open Policy Agent server instead.
"""
