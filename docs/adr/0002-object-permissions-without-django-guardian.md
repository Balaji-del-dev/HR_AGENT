# ADR 0002: Object-level permissions with tenant-scoped assignment tables

**Status:** Accepted, Phase 1 (2026-11-14)

## Context

The plan lists django-guardian for object-level permissions, such as "this recruiter is assigned to this requisition".

## Decision

Use explicit, tenant-scoped assignment models (the first is `RequisitionAssignment`) instead of django-guardian.

## Reasons

1. **Isolation.** Guardian keeps grants in generic tables (`content_type`, `object_pk` as text) with no `tenant_id`, so Row-Level Security cannot protect them ([ADR 0001](0001-tenant-isolation-with-row-level-security.md)). An assignment row is a `TenantScopedModel` and is isolated like any other tenant data.
2. **Queries.** Visibility is a plain `EXISTS` on a typed foreign key (`policies.visibility_filter`). It needs no text-to-UUID join over a generic table and indexes well.
3. **Compatibility.** django-guardian 3.5.2 declares support up to Django 6.0; the project runs Django 6.1.

## Consequences

- Each kind of grant gets its own small model, such as interview panel membership or offer approvers, and each one is under RLS.
- Decisions live in each app's `policies.py` as pure functions over an `ExecutionContext`. When OPA arrives, those functions become the adapter that asks it, and services do not change.
