/** Models service — health check and LLM model management. */

import { request } from './base.js';

export const healthCheck = () => request('/health');

export const listModels = () => request('/models');

export const selectModel = (model) =>
  request('/models/select', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });

export const loadModel = (model) =>
  request('/models/load', {
    method: 'POST',
    body: JSON.stringify({ model }),
  });
