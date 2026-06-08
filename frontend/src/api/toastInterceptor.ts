import { api } from './client';
import { extractApiError } from '../utils/extractApiError';
import { toast } from '../utils/toast';

// Global red-toast on any failed *mutation* (POST/PUT/PATCH/DELETE). Read
// requests and the auth/refresh flow are skipped so background 401s and polling
// failures don't spam the user. Success toasts are emitted explicitly by the
// action that performed the change (so the message is meaningful).
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const config = error?.config || {};
    const method = String(config.method || 'get').toLowerCase();
    const url = String(config.url || '');
    const isMutation = ['post', 'put', 'patch', 'delete'].includes(method);
    const isAuthFlow = url.includes('/auth/');
    const status = error?.response?.status;
    // Skip 401/403 (handled by auth refresh / route guards) and non-mutations.
    if (isMutation && !isAuthFlow && status !== 401 && status !== 403) {
      toast.error(extractApiError(error, 'Something went wrong. Please try again.'));
    }
    return Promise.reject(error);
  },
);
