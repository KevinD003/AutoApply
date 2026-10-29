"""What account deletion keeps, and what it cannot reach (docs/account-deletion.md).

This file holds the owner's retention decision, isolated so it can change in one place, with its
tests and the deletion preview reading it from here. NoEfforts has no legal retention policy:
nothing here is one. Until the owner decides otherwise (remaining-work "Owner decisions",
deletion retention), the default is the most protective that keeps every safety rule: nothing
about a deleted account is kept in NoEfforts' database, and deletion takes effect at once (no
grace period, no undo)."""

# Kept in NoEfforts' database after an account is deleted: nothing. Every row that names the
# account goes in one transaction, including its audit events, so no audit record of the account
# or of its deletion remains. Changing this is the owner's decision; it needs a table outside the
# account (every table that names one is deleted with it) and its own tests.
RETAINED_IN_DATABASE: tuple[str, ...] = ()

# Deletion takes effect at once; there is no grace period in which it could be undone.
GRACE_PERIOD_DAYS = 0

# What deletion cannot reach, shown before it and listed in docs/account-deletion.md.
OUTSIDE_NOEFFORTS: tuple[tuple[str, str], ...] = (
    (
        "employers",
        "Applications already sent are held by the employer or its application system. "
        "NoEfforts cannot delete them; ask the employer.",
    ),
    (
        "backups",
        "Backups made before the deletion still hold the account until they are deleted. "
        "Restoring one brings the account back (docs/deployment.md).",
    ),
    (
        "logs",
        "Server logs carry no applicant data by design (error types and route templates only) "
        "and are kept as long as the server's log settings keep them.",
    ),
    (
        "ai_provider",
        "If AI drafting was used, what was sent to the provider is kept under that provider's "
        "own terms. NoEfforts cannot delete it there.",
    ),
)
