import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import axios from 'axios';

test('OAuth UI uses existing JWT session, single exchange under StrictMode, safe errors and explicit linking', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.oauth-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://127.0.0.1:5173/' });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, Event: dom.window.Event,
        sessionStorage: dom.window.sessionStorage, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const { BrowserRouter, Routes, Route } = await import('react-router-dom');
    const previous = axios.defaults.adapter;
    const calls = [], navigations = [];
    globalThis.__oauthNavigate = (url) => navigations.push(url);
    let enabled = { google: true, github: false }, linked = { google: false, github: false }, failExchange = false;
    axios.defaults.adapter = async (config) => {
        calls.push(config);
        let data;
        if (config.url === 'users/oauth/providers/') data = enabled;
        else if (config.url === 'users/oauth/identities/') data = linked;
        else if (config.url.endsWith('/start/')) data = { authorization_url: 'https://provider.example/' + config.url };
        else if (config.url === 'users/oauth/exchange/' || config.url === 'token/') {
            if (failExchange) throw new Error('secret provider detail');
            data = { access: 'google-access', refresh: 'google-refresh' };
        } else if (config.url === 'users/me/') data = { username: 'france', email: 'france@example.com' };
        else if (config.url === 'users/logout/') data = {};
        else throw new Error(config.url);
        return { data, config, status: 200, headers: {}, statusText: 'OK' };
    };
    let root, auth;
    try {
        const entry = resolve(dir, 'entry.jsx');
        await writeFile(entry, `export {AuthProvider, useAuth} from '../../src/context/AuthContext.jsx';
export {default as Callback} from '../../src/pages/OAuthCallback.jsx';
export {default as Login} from '../../src/pages/login.jsx';
export {default as Account} from '../../src/components/AccountLogin.jsx';`);
        const bundle = await build({ logLevel: 'silent', plugins: [{ name: 'navigation-only', enforce: 'pre', transform(code, id) {
            if (id.replaceAll('\\', '/').endsWith('/services/oauth.js')) return code.replace('window.location.assign(', 'globalThis.__oauthNavigate(');
        } }], build: { write: false, minify: false, lib: { entry, formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|react-router-dom|axios)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'bundle.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((part) => part.type === 'chunk' && part.isEntry).code);
        const { AuthProvider, useAuth, Callback, Login, Account } = await import(pathToFileURL(file).href);
        function Consumer() { auth = useAuth(); return React.createElement('p', { id: 'user' }, auth.user?.username || 'guest'); }
        const render = async (element, path = '/') => {
            if (root) await act(async () => root.unmount());
            window.history.replaceState({}, '', path);
            root = createRoot(document.getElementById('root'));
            await act(async () => root.render(React.createElement(React.StrictMode, null,
                React.createElement(BrowserRouter, null, React.createElement(AuthProvider, null,
                    React.createElement(Consumer), element)))));
        };
        const button = (text) => [...document.querySelectorAll('button')].find((node) => node.textContent.includes(text));
        const click = async (node) => act(async () => node.dispatchEvent(new window.MouseEvent('click', { bubbles: true })));
        await render(React.createElement(Login));
        assert.ok(button('Přihlásit'));
        assert.ok(button('Pokračovat přes Google'));
        assert.equal(button('Pokračovat přes GitHub'), undefined);
        await click(button('Pokračovat přes Google'));
        assert.ok(navigations.at(-1).endsWith('users/oauth/google/start/'));
        assert.equal(calls.at(-1).withCredentials, true);
        enabled = { google: false, github: true };
        await render(React.createElement(Login));
        await click(button('Pokračovat přes GitHub'));
        assert.ok(navigations.at(-1).endsWith('users/oauth/github/start/'));
        const routes = React.createElement(Routes, null,
            React.createElement(Route, { path: '/oauth/callback', element: React.createElement(Callback) }),
            React.createElement(Route, { path: '/', element: React.createElement('p', { id: 'home' }, 'Home') }));
        await render(routes, '/oauth/callback?ticket=one-use');
        assert.equal(calls.filter((c) => c.url === 'users/oauth/exchange/').length, 1);
        assert.equal(auth.user.username, 'france');
        assert.equal(sessionStorage.getItem('access_token'), 'google-access');
        assert.equal(sessionStorage.getItem('refresh_token'), 'google-refresh');
        assert.equal(localStorage.getItem('access_token'), null);
        assert.ok(document.getElementById('home'));
        assert.equal(window.location.pathname, '/');
        assert.equal(window.location.search, '');
        assert.equal(calls.find((c) => c.url === 'users/me/').headers.Authorization, 'Bearer google-access');
        await act(async () => auth.logout());
        assert.equal(sessionStorage.getItem('access_token'), null);
        assert.equal(JSON.parse(calls.find((c) => c.url === 'users/logout/').data).refresh, 'google-refresh');
        // Password login uses the same completion method as OAuth.
        await act(async () => auth.login('france', 'password'));
        assert.equal(auth.user.username, 'france');
        await render(React.createElement(Account));
        const toggle = async () => act(async () => {
            const details = document.querySelector('details');
            details.open = true;
            details.dispatchEvent(new window.Event('toggle'));
        });
        await toggle();
        await click(button('Propojit GitHub'));
        assert.ok(navigations.at(-1).endsWith('users/oauth/github/link/start/'));
        assert.equal(calls.at(-1).headers.Authorization, 'Bearer google-access');
        linked.github = true;
        await render(routes, '/oauth/callback?linked=github');
        assert.equal(sessionStorage.getItem('access_token'), 'google-access');
        assert.equal(calls.filter((c) => c.url === 'users/oauth/exchange/').length, 1);
        await render(React.createElement(Account));
        await toggle();
        assert.match(document.body.textContent, /GitHub: propojeno/);
        assert.equal(button('Propojit GitHub'), undefined);
        for (const code of ['account_link_required', 'access_denied', 'untrusted-secret']) {
            await render(routes, '/oauth/callback?error=' + code);
            assert.ok(document.querySelector('[role="alert"]'));
            assert.ok(button('Zpět na přihlášení'));
            assert.equal(window.location.search, '');
            assert.ok(!document.body.textContent.includes('untrusted-secret'));
        }
        failExchange = true;
        await render(routes, '/oauth/callback?ticket=expired');
        assert.match(document.body.textContent, /Přihlášení se nezdařilo/);
        assert.ok(!document.body.textContent.includes('secret provider detail'));
    } finally {
        if (root) await act(async () => root.unmount());
        axios.defaults.adapter = previous;
        dom.window.close();
        delete globalThis.__oauthNavigate;
        assert.ok(dir.startsWith(resolve('node_modules') + sep + '.oauth-test-'));
        await rm(dir, { recursive: true, force: true });
    }
});
