"""Challenges and verification steps are checkpoints, never problems to solve.

NoEfforts may detect a challenge, keep the attempt's state, tell the user what is needed, and
resume only where that is lawful, supported and explicitly authorized. It never solves or
outsources a CAPTCHA, evades bot protection, bypasses access control, infers a code or a
credential, or reuses a code outside the attempt and round it was issued for."""

import enum
from dataclasses import dataclass


class CheckpointKind(enum.StrEnum):
    captcha = "captcha"
    bot_challenge = "bot_challenge"
    login_mfa = "login_mfa"
    sms_code = "sms_code"
    email_code = "email_code"
    identity_check = "identity_check"


@dataclass(frozen=True)
class CheckpointPolicy:
    automated: bool  # always False: no step is completed by NoEfforts itself
    resumable_in_noefforts: bool  # True only where the user enters the step themselves
    user_action: str


POLICY: dict[CheckpointKind, CheckpointPolicy] = {
    CheckpointKind.captcha: CheckpointPolicy(
        False, False, "The employer's page shows a CAPTCHA. NoEfforts does not solve or bypass "
        "these. Apply on the employer's site."),
    CheckpointKind.bot_challenge: CheckpointPolicy(
        False, False, "The employer's page shows a bot check. NoEfforts stops here and does not "
        "try to get past it. Apply on the employer's site."),
    CheckpointKind.login_mfa: CheckpointPolicy(
        False, False, "The employer asks you to sign in with a second factor. NoEfforts does "
        "not sign in for you. Apply on the employer's site."),
    CheckpointKind.sms_code: CheckpointPolicy(
        False, False, "The employer sent a code to your phone. Text-message codes are not "
        "supported. Apply on the employer's site."),
    CheckpointKind.email_code: CheckpointPolicy(
        False, True, "Enter the code the employer emailed you. It is used once, for this "
        "attempt only, and is not stored."),
    CheckpointKind.identity_check: CheckpointPolicy(
        False, False, "The employer asks you to verify your identity. NoEfforts does not do "
        "this for you. Apply on the employer's site."),
}  # fmt: skip


def user_action(kind: CheckpointKind) -> str:
    return POLICY[kind].user_action
