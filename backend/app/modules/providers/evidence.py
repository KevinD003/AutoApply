"""The evidence classes NoEfforts keeps apart everywhere (docs/upload-and-submission-evidence.md,
"Evidence classes", is tested against this). A class says where a piece of evidence came from;
it never stands in for another class, and none of them is support on its own."""

EVIDENCE_CLASSES: dict[str, str] = {
    "fixture": "a run against a local, fictional test fixture",
    "public_doc_expectation": "what public documentation describes; unverified, never seen",
    "read_only_observation": "a real page seen read-only in an approved run; never filled there",
    "rehearsal": "a real form filled and checked under an approval to disclose only; nothing "
    "submitted",
    "real_submission": "a real final submit with an attempt-bound confirmation",
}
