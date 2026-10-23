"""What a package may send. One rule, used by the package builder, the runner and every adapter:
an answer is sent only when its status is `resolved`.

A row that is not resolved can still carry a value for review: a sensitive answer waiting for
consent, or an accepted draft whose facts changed. Both block approval (package.build_content
lists them as unresolved), so no approved package has one; a blank optional row carries none.
"""


def sendable(a: dict) -> bool:
    return a["status"] == "resolved" and a["value"] is not None


def unsendable(content: dict) -> int:
    """How many answers carry a value they may not send. Zero for every approved package: the
    runner refuses one that is not, before any adapter code runs."""
    return sum(1 for a in content["answers"] if a["value"] is not None and not sendable(a))


def sendable_view(content: dict) -> dict:
    """The package as an adapter fills, uploads and reads it back: an answer that is not
    resolved has no value, and only resolved answers' documents are attached. The runner has
    already refused a package this changes; adapters apply it too, so none can send such a
    row."""
    keep = {a["key"] for a in content["answers"] if sendable(a)}
    return {
        **content,
        "answers": [a if sendable(a) else {**a, "value": None} for a in content["answers"]],
        "documents": [d for d in content["documents"] if d["field"] in keep],
    }
