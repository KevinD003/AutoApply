"""Import every model so Alembic and metadata.create_all see the full schema."""

from app.modules.applications.models import Application, ApplicationEvent  # noqa: F401
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.documents.models import Document  # noqa: F401
from app.modules.identity.models import User, UserSession  # noqa: F401
from app.modules.jobs.models import ImportBatch, Job  # noqa: F401
from app.modules.profiles.models import (  # noqa: F401
    CandidateProfile,
    Credential,
    EducationRecord,
    EmploymentRecord,
    FactVersion,
    JobPreferences,
    WorkAuthorization,
)
