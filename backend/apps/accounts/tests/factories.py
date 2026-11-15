import factory
from factory.django import DjangoModelFactory, Password

from apps.accounts.models import Membership, User
from apps.accounts.roles import Role
from apps.core.tests.factories import TenantFactory


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    username = factory.Sequence(lambda n: f"user{n}")
    email = factory.LazyAttribute(lambda user: f"{user.username}@example.test")
    password = Password("test-password")


class MembershipFactory(DjangoModelFactory[Membership]):
    class Meta:
        model = Membership

    tenant = factory.SubFactory(TenantFactory)
    user = factory.SubFactory(UserFactory)
    roles = factory.LazyFunction(lambda: [Role.RECRUITER.value])
