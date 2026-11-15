from django.db import models


class Role(models.TextChoices):
    """Roles a user holds inside one tenant (see Membership.roles).

    Platform super admins are Django superusers with no membership, so by
    default they see no candidate data at all.
    """

    HR_ADMIN = "hr_admin", "HR admin"
    RECRUITER = "recruiter", "Recruiter"
    HIRING_MANAGER = "hiring_manager", "Hiring manager"
    INTERVIEWER = "interviewer", "Interviewer"
    FINANCE_APPROVER = "finance_approver", "Finance approver"
    AUDITOR = "auditor", "Auditor"
