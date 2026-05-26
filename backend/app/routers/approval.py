"""Exam paper multi-stage approval workflow controller."""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from app.auth import get_current_user
from app.database import (
    delete_submission,
    get_submission_full,
    list_approval_officers,
    list_my_submissions,
    list_pending_for_officer,
    list_processed_by_officer,
    process_approval_action,
    submit_exam_for_approval,
    update_submission_questions,
)
from app.models import ApprovalActionRequest, SubmitApprovalRequest
from app.utils.sanitizer import sanitize_user_input

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approval", tags=["approval"])


@router.get("/officers")
def api_get_officers(_user: dict = Depends(get_current_user)):
    """Return list of users who can act as approval officers."""
    return list_approval_officers()


@router.post("/submit", status_code=201)
def api_submit_exam(body: SubmitApprovalRequest, user: dict = Depends(get_current_user)):
    """Submit an exam paper for multi-stage approval."""
    if not body.stages:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "At least one approval stage required")
    if len(body.stages) > 3:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Maximum 3 approval stages allowed")

    # Validate that every nominated officer actually has approval access
    officers_map = {o["id"]: o["username"] for o in list_approval_officers()}
    for stage_cfg in body.stages:
        if stage_cfg.officer_id not in officers_map:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"User {stage_cfg.officer_id!r} does not have approval access",
            )

    stages = [
        {"officer_id": s.officer_id, "officer_name": officers_map[s.officer_id]}
        for s in body.stages
    ]

    title = sanitize_user_input(body.title, max_length=200)
    sub = submit_exam_for_approval(
        created_by=user["sub"],
        conversation_id=body.conversation_id or "",
        title=title,
        questions=body.questions,
        header=body.header,
        raw_text=sanitize_user_input(body.raw_text or "", max_length=50000),
        stages=stages,
    )
    log.info("Exam submission %s created by user %s", sub["id"], user["sub"])
    return sub


@router.get("/my-submissions")
def api_my_submissions(user: dict = Depends(get_current_user)):
    """Return all submissions created by the current user."""
    return list_my_submissions(user["sub"])


@router.get("/pending")
def api_pending(user: dict = Depends(get_current_user)):
    """Return submissions pending review by the current user (as officer)."""
    return list_pending_for_officer(user["sub"])


@router.get("/history")
def api_history(user: dict = Depends(get_current_user)):
    """Return submissions already reviewed by the current user (as officer)."""
    return list_processed_by_officer(user["sub"])


@router.get("/{submission_id}")
def api_get_submission(submission_id: str, user: dict = Depends(get_current_user)):
    """Return full details of a submission.  Accessible to creator, assigned officers, or admins."""
    sub = get_submission_full(submission_id)
    if not sub:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    is_creator = sub["created_by"] == user["sub"]
    is_officer = any(s["officer_id"] == user["sub"] for s in sub.get("stages", []))
    if not is_creator and not is_officer and user.get("role") != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Access denied")
    return sub


@router.delete("/{submission_id}", status_code=204)
def api_delete_submission(submission_id: str, user: dict = Depends(get_current_user)):
    """Creator can delete their own pending submission."""
    try:
        ok = delete_submission(submission_id, user["sub"])
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Submission not found")
    log.info("Submission %s deleted by user %s", submission_id, user["sub"])


@router.post("/{submission_id}/action")
def api_action(
    submission_id: str,
    body: ApprovalActionRequest,
    user: dict = Depends(get_current_user),
):
    """Officer approves or sends back an exam submission."""
    remark = sanitize_user_input(body.remark or "", max_length=2000)
    try:
        updated = process_approval_action(
            submission_id=submission_id,
            officer_id=user["sub"],
            action=body.action,
            remark=remark,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    log.info("Submission %s actioned '%s' by officer %s", submission_id, body.action, user["sub"])
    return updated


@router.patch("/{submission_id}/questions")
def api_update_questions(
    submission_id: str,
    body: dict,
    user: dict = Depends(get_current_user),
):
    """Owner or assigned officer updates the questions of a submission."""
    questions = body.get("questions", [])
    if not isinstance(questions, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "questions must be a list")
    try:
        updated = update_submission_questions(
            submission_id=submission_id,
            user_id=user["sub"],
            questions=questions,
            user_role=user.get("role", "user"),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    log.info("Submission %s questions updated by user %s", submission_id, user["sub"])
    return updated
