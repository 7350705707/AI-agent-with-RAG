/** Exam approval workflow API calls. */
import { request } from './base.js';

/** Return users who have the 'approval' agent (eligible officers). */
export const getApprovalOfficers = () => request('/approval/officers');

/** Submit an exam paper for multi-stage approval. */
export const submitExamForApproval = (data) =>
  request('/approval/submit', { method: 'POST', body: JSON.stringify(data) });

/** Return all submissions created by the current user. */
export const getMySubmissions = () => request('/approval/my-submissions');

/** Return submissions pending review by the current user (officer queue). */
export const getPendingReviews = () => request('/approval/pending');

/** Return submissions already reviewed by the current user (officer history). */
export const getApprovalHistory = () => request('/approval/history');

/** Return full details of a single submission. */
export const getSubmission = (submissionId) =>
  request(`/approval/${submissionId}`);

/** Officer approves or sends back a submission. */
export const submitApprovalAction = (submissionId, action, remark = '') =>
  request(`/approval/${submissionId}/action`, {
    method: 'POST',
    body: JSON.stringify({ action, remark }),
  });

export const deleteSubmission = (submissionId) =>
  request(`/approval/${submissionId}`, { method: 'DELETE' });

/** Owner or officer updates the questions of a submission. */
export const updateSubmissionQuestions = (submissionId, questions) =>
  request(`/approval/${submissionId}/questions`, {
    method: 'PATCH',
    body: JSON.stringify({ questions }),
  });

/** Creator resubmits a sent_back submission with updated questions and a new approval chain. */
export const resubmitForApproval = (submissionId, questions, stages) =>
  request(`/approval/${submissionId}/resubmit`, {
    method: 'POST',
    body: JSON.stringify({ questions, stages }),
  });
