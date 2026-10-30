"""Persist AI artifacts and their source revision in the caller's transaction."""
import uuid

from sqlalchemy import select

from .models import WorkspaceVersion

RESULT_FIELDS = {"rewrite": "rewrite_text", "summary": "summary_text", "translate": "translated_text", "highlights": "highlights", "visual": "visual_analysis"}


def save_result(db, task, kind: str, content: dict, *, origin="generated", source_revision=None):
    field = RESULT_FIELDS[kind]
    old_value = getattr(task, field)
    # Preserve results generated before version history was introduced.
    if old_value and not db.scalar(select(WorkspaceVersion.id).where(
        WorkspaceVersion.task_id == task.id, WorkspaceVersion.kind == kind,
    ).limit(1)):
        previous = {"value": old_value}
        if kind == "translate":
            previous["language"] = task.translation_language
        db.add(WorkspaceVersion(id=str(uuid.uuid4()), task_id=task.id, kind=kind,
            content=previous, source_revision=(task.result_revisions or {}).get(kind, 1), origin="legacy"))
    setattr(task, field, content["value"])
    if kind == "translate":
        task.translation_language = content.get("language")
    revision = source_revision if source_revision is not None else (task.transcript_revision or 1)
    task.result_revisions = {**(task.result_revisions or {}), kind: revision}
    version = WorkspaceVersion(id=str(uuid.uuid4()), task_id=task.id, kind=kind,
        content=content, source_revision=revision, origin=origin)
    db.add(version)
    return version
