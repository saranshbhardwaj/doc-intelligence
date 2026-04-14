import { createAuthenticatedApi } from './client';

export async function getTemplateFillAnalytics(getToken) {
  const authenticatedApi = createAuthenticatedApi(getToken);
  const response = await authenticatedApi.get('/api/admin/template-fill-analytics');
  return response.data;
}
