/** Analytics service */
import { request } from './base.js';

export const getAnalyticsSummary = () => request('/analytics/summary');
export const getMyAnalytics = () => request('/analytics/me');
