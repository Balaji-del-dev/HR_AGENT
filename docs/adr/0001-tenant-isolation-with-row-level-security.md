# ADR 0001: Tenant isolation with PostgreSQL Row-Level Security

**Status:** Accepted, Phase 1 (2026-11-14)

## Context

The plan requires that one tenant can never read another tenant's data, even if application code has a bug. App-level filters alone (`.filter(tenant=...)`) fail silently the first time someone forgets one.

## Decision

Two independent fences:

1. **App fence.** Selectors filter by `ctx.tenant_id` explicitly.
2. **Database fence.** Every tenant-owned table has Row-Level Security with one policy:

   ```sql
   USING      (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
   WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)
   ```

How the pieces fit:

| Piece | Where | Why |
|---|---|---|
| Two DB roles | `scripts/setup_local_db.sql` | `hr_owner` owns tables and runs migrations. The app connects as `hr_app`, which neither owns the tables nor has BYPASSRLS. Table owners bypass RLS, so the app must never connect as the owner. |
| Grants | `apps/core/db/privileges.py` (post_migrate) | `hr_app` gets SELECT/INSERT/UPDATE/DELETE on every table. It gets no TRUNCATE (TRUNCATE ignores RLS) and no DDL. |
| Policy per table | `EnableRowLevelSecurity` migration operation | Added by hand after `CreateModel`. `test_every_tenant_table_has_rls` fails CI if a `TenantScopedModel` lacks it. |
| Tenant setting | `apps/core/tenancy.py` | `set_config('app.tenant_id', id, true)`: transaction-local, so it cannot leak to the next request on a pooled connection. |
| API requests | `TenantContextMixin.perform_authentication` | DRF authenticates inside the view, so the tenant is activated there, right after authentication and before permission checks. `ATOMIC_REQUESTS=True` supplies the transaction. |
| Celery tasks | `TenantTask` | Each task declares `tenant_id` and runs inside `tenant_scope(tenant_id)`. |
| Middleware | `RequestContextMiddleware` | Clears any active tenant before and after every request. |

### Details that matter

- **`NULLIF(..., '')`.** Once a transaction that set the value ends, `current_setting` returns `''`, not NULL. `''::uuid` raises an error; NULLIF turns "no tenant" into NULL, which matches no rows. No tenant means no rows, not an error.
- **Nested scopes.** `SET LOCAL` survives `RELEASE SAVEPOINT`, so `tenant_scope` restores the outer tenant explicitly on normal exit.
- **Tests run as the runtime role.** The suite connects as `hr_owner` (it creates the test database), and `conftest.py` runs `SET ROLE hr_app` for every DB test. Without this the tests would bypass RLS and pass while production leaked.
- **Not under RLS:** `core_tenant`, `accounts_user` and `accounts_membership`. These identity tables are read to decide which tenant to activate. Access goes only through `apps.accounts.selectors`.

## Differences from the plan

- The plan says middleware calls `set_config`. Middleware runs before DRF knows the user, so activation happens in the base view instead, and middleware only guarantees cleanup.
- Django admin runs with no tenant active, so it shows no tenant-owned rows. That matches the plan: admin is for configuration, not for browsing records.

## Known gap

Foreign-key checks bypass RLS. A row in tenant A could reference a row ID from tenant B if code passed one in. Services only link objects fetched through tenant-scoped selectors. Composite foreign keys on `(tenant_id, id)` would close the gap in the database; revisit in the hardening phase.
