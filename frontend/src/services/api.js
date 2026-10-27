import axios from "axios";

// Legacy shared credentials must never authorize requests.
localStorage.removeItem("access_token");
localStorage.removeItem("refresh_token");

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || (import.meta.env.DEV ? "http://127.0.0.1:8000/api/" : "/api/")).replace(/\/?$/, "/");
const transport = axios.create({ baseURL: API_BASE_URL, timeout: 15000 });
const api = axios.create({ baseURL: API_BASE_URL });
let sessionVersion = 0;
let refreshFlight = null;
export const getSessionVersion = () => sessionVersion;

export function clearSession() {
    sessionVersion += 1;
    sessionStorage.removeItem("access_token");
    sessionStorage.removeItem("refresh_token");
    window.dispatchEvent(new Event("auth-cleared"));
}

export function startSession({ access, refresh }) {
    clearSession();
    sessionStorage.setItem("access_token", access);
    sessionStorage.setItem("refresh_token", refresh);
}

const publicAuth = (url) => ["token/", "token/refresh/", "users/register/",
    "users/oauth/providers/", "users/oauth/exchange/", "users/oauth/google/start/", "users/oauth/github/start/"].includes(url);
api.interceptors.request.use((config) => {
    if (config._sessionVersion !== undefined && config._sessionVersion !== sessionVersion) {
        throw new axios.CanceledError("Session changed");
    }
    config._sessionVersion = sessionVersion;
    const token = sessionStorage.getItem("access_token");
    if (token && !publicAuth(config.url)) config.headers.Authorization = `Bearer ${token}`;
    else delete config.headers.Authorization;
    return config;
});

function refreshSession() {
    const version = sessionVersion;
    if (refreshFlight?.version === version) return refreshFlight.promise;
    const refresh = sessionStorage.getItem("refresh_token");
    if (!refresh) { clearSession(); return Promise.reject(new Error("No session")); }
    const flight = { version };
    flight.promise = transport.post("token/refresh/", { refresh }).then(({ data }) => {
        if (sessionVersion !== version) throw new axios.CanceledError("Session changed");
        sessionStorage.setItem("access_token", data.access);
        sessionStorage.setItem("refresh_token", data.refresh);
        return data.access;
    }).catch((error) => {
        if (sessionVersion === version) clearSession();
        throw error;
    }).finally(() => {
        if (refreshFlight === flight) refreshFlight = null;
    });
    refreshFlight = flight;
    return flight.promise;
}

api.interceptors.response.use((response) => {
    if (response.config._sessionVersion !== sessionVersion) throw new axios.CanceledError("Session changed");
    return response;
}, async (error) => {
    const request = error.config;
    if (!request || error.response?.status !== 401 || request._retry || publicAuth(request.url)
        || request._sessionVersion !== sessionVersion) throw error;
    request._retry = true;
    // A late 401 from the old access token can reuse an already completed refresh.
    const current = sessionStorage.getItem("access_token");
    if (!current || request.headers.Authorization === `Bearer ${current}`) await refreshSession();
    return api(request);
});

export async function revokeSession() {
    const version = sessionVersion;
    // Finish any rotation before revoking its replacement token.
    if (refreshFlight?.version === version) {
        try { await refreshFlight.promise; } catch { return; }
    }
    if (version !== sessionVersion) return;
    const refresh = sessionStorage.getItem("refresh_token");
    const access = sessionStorage.getItem("access_token");
    clearSession();
    if (refresh && access) {
        // Never restore browser credentials while revoking an expired session.
        try {
            await transport.post("users/logout/", { refresh }, { headers: { Authorization: `Bearer ${access}` } });
        } catch (error) {
            if (error.response?.status === 401) {
                try {
                    const { data } = await transport.post("token/refresh/", { refresh });
                    await transport.post("users/logout/", { refresh: data.refresh },
                        { headers: { Authorization: `Bearer ${data.access}` } });
                } catch { /* Offline/invalid token: local logout still succeeds. */ }
            }
        }
    }
}

export default api;
