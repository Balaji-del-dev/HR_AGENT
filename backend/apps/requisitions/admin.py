# Tenant-owned data is not registered in Django admin. Admin is for HR admins
# to manage platform configuration, not for browsing tenant records, and it
# runs without an active tenant, so Row-Level Security would hide every row.
