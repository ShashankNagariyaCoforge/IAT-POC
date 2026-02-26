/**
 * MSAL configuration for Azure AD authentication.
 * Uses environment variables injected at build time by Vite.
 */

import { Configuration, LogLevel } from '@azure/msal-browser';

export const msalConfig: Configuration = {
    auth: {
        clientId: import.meta.env.VITE_AZURE_AD_CLIENT_ID || '',
        authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_AD_TENANT_ID || 'common'}`,
        redirectUri: window.location.origin,
        postLogoutRedirectUri: window.location.origin,
    },
    cache: {
        cacheLocation: 'sessionStorage',
        storeAuthStateInCookie: false,
    },
    system: {
        loggerOptions: {
            loggerCallback: (level, message, containsPii) => {
                if (containsPii) return;
                if (level === LogLevel.Error) console.error(message);
                else if (level === LogLevel.Warning) console.warn(message);
            },
        },
    },
};

/** Scopes required for calling the backend API. */
export const loginRequest = {
    scopes: ['openid', 'profile', 'email'],
};

/** Scopes for acquiring tokens to call the backend API. */
export const apiRequest = {
    scopes: [`api://${import.meta.env.VITE_AZURE_AD_CLIENT_ID || ''}/access_as_user`],
};
