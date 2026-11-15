"""Evaluation suites: golden datasets and the gate every prompt, model or graph change must pass.

Run with ``manage.py run_evals`` (uses the configured LLM provider). CI runs the
offline provider for a fast regression gate; nightly runs use the real model.
"""
