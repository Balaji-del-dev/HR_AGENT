"""Resume text pipeline: validate, scan, extract, sanitize, segment, mask.

Pure functions over bytes and strings, with no Django models, so each step is
easy to test. apps.documents.tasks runs them in order on the documents queue.
"""
