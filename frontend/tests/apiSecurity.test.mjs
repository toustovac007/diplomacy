import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';
import axios from 'axios';

test('per-tab auth rotates once, rejects stale sessions, and revokes logout', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.auth-test-'));
    const previousAdapter = axios.defaults.adapter;
    const storage = () => {
        const items = new Map();
        return { getItem: (key) => items.get(key) ?? null, setItem: (key, value) => items.set(key, value), removeItem: (key) => items.delete(key) };
    };
    globalThis.sessionStorage = storage();
    globalThis.localStorage = storage();
    globalThis.window = new EventTarget();
    localStorage.setItem('access_token', 'legacy');
    const calls = [];
    let releaseRefresh;
    let refreshGate;
    axios.defaults.adapter = async (config) => {
        calls.push(config);
        const reply = (data) => ({ data, status: 200, statusText: 'OK', headers: {}, config });
        const unauthorized = () => { throw new axios.AxiosError('unauthorized', 'ERR_BAD_REQUEST', config, null,
            { data: {}, status: 401, headers: {}, config }); };
        if (config.url === 'token/refresh/') {
            if (refreshGate) await refreshGate;
            if (JSON.parse(config.data).refresh === 'invalid') return unauthorized();
            return reply({ access: 'new-access', refresh: 'new-refresh' });
        }
        if (config.url === 'token/') return unauthorized();
        if (config.url === 'users/logout/') {
            if (config.headers.Authorization === 'Bearer expired-access') return unauthorized();
            return reply({});
        }
        if (config.headers.Authorization === 'Bearer old-access') return unauthorized();
        return reply({ username: 'alice' });
    };
    try {
        const bundle = await build({ logLevel: 'silent', define: { 'import.meta.env.VITE_API_BASE_URL': JSON.stringify('https://api.example/api/') },
            build: { write: false, minify: false, lib: { entry: resolve('src/services/api.js'), formats: ['es'] },
                rolldownOptions: { external: ['axios'] } } });
        const file = resolve(dir, 'api.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((part) => part.type === 'chunk' && part.isEntry).code);
        const { default: api, startSession, clearSession, revokeSession, API_BASE_URL } = await import(pathToFileURL(file).href);
        assert.equal(API_BASE_URL, 'https://api.example/api/');
        assert.equal(localStorage.getItem('access_token'), null);
        startSession({ access: 'old-access', refresh: 'old-refresh' });
        await Promise.all([api.get('games/'), api.get('users/me/'), api.get('notifications/preferences/')]);
        assert.equal(calls.filter((c) => c.url === 'token/refresh/').length, 1);
        assert.equal(sessionStorage.getItem('access_token'), 'new-access');
        assert.equal(sessionStorage.getItem('refresh_token'), 'new-refresh');
        assert.ok(calls.every((c) => c.baseURL === API_BASE_URL));
        await assert.rejects(api.post('token/', { username: 'alice', password: 'wrong' }));
        assert.equal(calls.filter((c) => c.url === 'token/refresh/').length, 1);
        assert.equal(calls.find((c) => c.url === 'token/').headers.Authorization, undefined);
        for (const url of ['users/oauth/providers/', 'users/oauth/google/start/', 'users/oauth/github/start/', 'users/oauth/exchange/']) {
            await api.post(url, {});
            assert.equal(calls.at(-1).headers.Authorization, undefined);
        }
        for (const url of ['users/oauth/identities/', 'users/oauth/google/link/start/', 'users/oauth/github/link/start/']) {
            await api.post(url, {});
            assert.equal(calls.at(-1).headers.Authorization, 'Bearer new-access');
        }
        await revokeSession();
        assert.equal(JSON.parse(calls.find((c) => c.url === 'users/logout/').data).refresh, 'new-refresh');
        assert.equal(sessionStorage.getItem('access_token'), null);

        startSession({ access: 'expired-access', refresh: 'expired-session-refresh' });
        await revokeSession();
        assert.equal(sessionStorage.getItem('refresh_token'), null);
        assert.equal(JSON.parse(calls.filter((c) => c.url === 'users/logout/').at(-1).data).refresh, 'new-refresh');

        // An old refresh must never overwrite a newly logged-in account.
        startSession({ access: 'old-access', refresh: 'old-refresh' });
        refreshGate = new Promise((resolve) => { releaseRefresh = resolve; });
        const pending = api.get('games/');
        const rejected = assert.rejects(pending);
        while (calls.filter((c) => c.url === 'token/refresh/').length < 3) await new Promise((resolve) => setImmediate(resolve));
        startSession({ access: 'england-access', refresh: 'england-refresh' });
        releaseRefresh();
        await rejected;
        assert.equal(sessionStorage.getItem('access_token'), 'england-access');
        assert.equal(sessionStorage.getItem('refresh_token'), 'england-refresh');
        refreshGate = null;
        startSession({ access: 'old-access', refresh: 'invalid' });
        await assert.rejects(api.get('games/'));
        assert.equal(sessionStorage.getItem('refresh_token'), null);
        clearSession();

        // Independent module/window/storage realms model two already-open tabs.
        // Both use the exact same bundled API implementation and shared legacy storage.
        const code = (Array.isArray(bundle) ? bundle[0] : bundle).output.find((part) => part.type === 'chunk' && part.isEntry).code;
        globalThis.__tabA = { sessionStorage: storage(), localStorage, window: new EventTarget() };
        globalThis.__tabB = { sessionStorage: storage(), localStorage, window: new EventTarget() };
        for (const name of ['A', 'B']) {
            await writeFile(resolve(dir, `tab${name}.mjs`), `const {sessionStorage,localStorage,window}=globalThis.__tab${name};\n` + code);
        }
        const tabA = await import(pathToFileURL(resolve(dir, 'tabA.mjs')).href);
        const tabB = await import(pathToFileURL(resolve(dir, 'tabB.mjs')).href);
        tabA.startSession({ access: 'france-access', refresh: 'france-refresh' });
        tabB.startSession({ access: 'england-access', refresh: 'england-refresh' });
        await tabA.default.get('users/me/');
        assert.equal(calls.at(-1).headers.Authorization, 'Bearer france-access');
        await tabB.default.get('users/me/');
        assert.equal(calls.at(-1).headers.Authorization, 'Bearer england-access');
        await tabB.revokeSession();
        assert.equal(globalThis.__tabB.sessionStorage.getItem('access_token'), null);
        await tabA.default.get('users/me/');
        assert.equal(calls.at(-1).headers.Authorization, 'Bearer france-access');
        assert.equal(globalThis.__tabA.sessionStorage.getItem('refresh_token'), 'france-refresh');
    } finally {
        axios.defaults.adapter = previousAdapter;
        delete globalThis.sessionStorage;
        delete globalThis.localStorage;
        delete globalThis.window;
        delete globalThis.__tabA;
        delete globalThis.__tabB;
        assert.ok(dir.startsWith(resolve('node_modules') + sep + '.auth-test-'));
        await rm(dir, { recursive: true, force: true });
    }
});
