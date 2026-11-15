from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts.models import Membership, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin[User]):
    fieldsets = (*DjangoUserAdmin.fieldsets, ("Identity provider", {"fields": ("oidc_subject",)}))  # type: ignore[misc]
    list_display = ("username", "email", "is_staff", "is_active")


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin[Membership]):
    list_display = ("user", "tenant", "roles", "is_active")
    list_filter = ("is_active", "tenant")
    search_fields = ("user__username", "user__email", "tenant__name")
    autocomplete_fields = ("user",)
