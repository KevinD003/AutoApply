"""Import every model so Alembic and metadata.create_all see the full schema."""

from app.modules.apitokens.models import ApiToken  # noqa: F401
from app.modules.applications.models import Application, ApplicationEvent  # noqa: F401
from app.modules.audit.models import AuditEvent  # noqa: F401
from app.modules.discovery.models import DiscoveredJob  # noqa: F401
from app.modules.documents.models import Document  # noqa: F401
from app.modules.execution.models import (  # noqa: F401
    AttemptEvent,
    Checkpoint,
    Evidence,
    ExecutionAttempt,
    OutboxMessage,
)
from app.modules.followups.models import FollowUp  # noqa: F401
from app.modules.identity.models import User, UserSession  # noqa: F401
from app.modules.jobs.models import ImportBatch, Job  # noqa: F401
from app.modules.mail.models import EmailDelivery, EmailSettings  # noqa: F401
from app.modules.notifications.models import NotificationRead  # noqa: F401
from app.modules.preparation.models import (  # noqa: F401
    AnswerBankEntry,
    AnswerDraft,
    ApplicationInput,
    ApplicationPackage,
    JobForm,
    PackageApproval,
)
from app.modules.profiles.models import (  # noqa: F401
    CandidateProfile,
    Credential,
    EducationRecord,
    EmploymentRecord,
    FactVersion,
    JobPreferences,
    WorkAuthorization,
)
from app.modules.providers.models import ApiAuthorization  # noqa: F401
