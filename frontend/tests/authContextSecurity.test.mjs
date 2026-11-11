import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import axios from 'axios';

test('AuthContext loads the same account after initial token rotation and clears on logout', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.auth-context-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, Event: dom.window.Event,
        sessionStorage: dom.window.sessionStorage, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const oldAdapter = axios.defaults.adapter;
    const calls = [];
    axios.defaults.adapter = async (config) => {
        calls.push(config);
        if (config.url === 'users/me/' && config.headers.Authorization === 'Bearer expired') {
            throw new axios.AxiosError('expired', 'ERR_BAD_REQUEST', config, null, { status: 401, data: {}, config });
        }
        const data = config.url === 'token/refresh/' ? { access: 'access2', refresh: 'refresh2' }
            : { username: 'france', email: 'france@example.test' };
        return { data, config, status: 200, headers: {}, statusText: 'OK' };
    };
    let root;
    try {
        const bundle = await build({ logLevel: 'silent', build: { write: false, minify: false,
            lib: { entry: resolve('src/context/AuthContext.jsx'), formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|axios)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'context.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { AuthProvider, useAuth } = await import(pathToFileURL(file).href);
        sessionStorage.setItem('access_token', 'expired');
        sessionStorage.setItem('refresh_token', 'refresh1');
        let auth;
        function Consumer() {
            auth = useAuth();
            return React.createElement('p', null, auth.user?.username ?? 'logged out');
        }
        root = createRoot(document.getElementById('root'));
        await act(async () => root.render(React.createElement(AuthProvider, null, React.createElement(Consumer))));
        assert.equal(auth.loading, false);
        assert.equal(auth.user.username, 'france');
        assert.equal(sessionStorage.getItem('refresh_token'), 'refresh2');
        assert.equal(calls.filter((call) => call.url === 'token/refresh/').length, 1);
        await act(async () => auth.logout());
        assert.equal(auth.user, null);
        assert.equal(sessionStorage.getItem('access_token'), null);
        assert.equal(JSON.parse(calls.find((call) => call.url === 'users/logout/').data).refresh, 'refresh2');
    } finally {
        if (root) await act(async () => root.unmount());
        axios.defaults.adapter = oldAdapter;
        dom.window.close();
        assert.ok(dir.startsWith(resolve('node_modules') + sep + '.auth-context-test-'));
        await rm(dir, { recursive: true, force: true });
    }
});
