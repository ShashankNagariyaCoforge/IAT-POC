/**
 * API client for all backend calls.
 * Automatically injects the Azure AD Bearer token from MSAL.
 */

import axios, { AxiosInstance } from 'axios';
import { IPublicClientApplication, InteractionRequiredAuthError } from '@azure/msal-browser';
import { apiRequest } from '../auth/msalConfig';
import type {
    CaseListResponse,
    Case,
    Email,
    Document,
    ClassificationResult,
    TimelineEvent,
    Stats,
    PipelineStatus,
} from '../types';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const DEV_BYPASS_AUTH = import.meta.env.VITE_DEV_BYPASS_AUTH === 'true';

/** Build an Axios instance that auto-attaches the Bearer token. */
export function createApiClient(msalInstance: IPublicClientApplication): AxiosInstance {
    const client = axios.create({
        baseURL: `${BASE_URL}/api`,
        timeout: 300000, // 5 minutes for bulk AI processing
    });

    client.interceptors.request.use(async (config) => {
        // Skip token attachment entirely in dev bypass mode
        if (DEV_BYPASS_AUTH) return config;

        try {
            const accounts = msalInstance.getAllAccounts();
            if (accounts.length > 0) {
                const tokenResponse = await msalInstance.acquireTokenSilent({
                    ...apiRequest,
                    account: accounts[0],
                });
                config.headers['Authorization'] = `Bearer ${tokenResponse.accessToken}`;
            }
        } catch (err) {
            if (err instanceof InteractionRequiredAuthError) {
                await msalInstance.acquireTokenRedirect(apiRequest);
            }
        }
        return config;
    });

    return client;
}

export interface ListCasesParams {
    page?: number;
    page_size?: number;
    search?: string;
    category?: string;
    status?: string;
    requires_human_review?: boolean;
    date_from?: string;
    date_to?: string;
    sort_by?: string;
    sort_order?: 'ASC' | 'DESC';
}

/** All API functions — used by pages and components. */
export const casesApi = {
    listCases: (client: AxiosInstance, params: ListCasesParams = {}) =>
        client.get<CaseListResponse>('/cases', { params }).then((r) => r.data),

    getCase: (client: AxiosInstance, caseId: string) =>
        client.get<Case>(`/cases/${caseId}`).then((r) => r.data),

    getCaseEmails: (client: AxiosInstance, caseId: string) =>
        client.get<{ emails: Email[]; total: number }>(`/cases/${caseId}/emails`).then((r) => r.data),

    getCaseDocuments: (client: AxiosInstance, caseId: string) =>
        client.get<{ documents: Document[]; total: number }>(`/cases/${caseId}/documents`).then((r) => r.data),

    getCaseClassification: (client: AxiosInstance, caseId: string) =>
        client.get<{ classification: ClassificationResult | null }>(`/cases/${caseId}/classification`).then((r) => r.data),

    getCaseTimeline: (client: AxiosInstance, caseId: string) =>
        client.get<{ timeline: TimelineEvent[] }>(`/cases/${caseId}/timeline`).then((r) => r.data),

    getStats: (client: AxiosInstance) =>
        client.get<Stats>('/stats').then((r) => r.data),

    getPipelineStatus: (client: AxiosInstance, caseId: string) =>
        client.get<PipelineStatus>(`/cases/${caseId}/pipeline-status`).then((r) => r.data),
};
