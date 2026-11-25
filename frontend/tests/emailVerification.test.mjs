import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import axios from 'axios';

test('email verification needs an explicit click, clears the URL, never logs in, and supports invalid links and resend', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.verification-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/verify-email#token=secret-proof' });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, Event: dom.window.Event,
        sessionStorage: dom.window.sessionStorage, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const previous = axios.defaults.adapter;
    const calls = [];
    let failure = 0, root, loginFailure = false;
    axios.defaults.adapter = async (config) => {
        calls.push(config);
        if (loginFailure && config.url === 'token/') throw new axios.AxiosError('unverified', undefined, config, {},
            { status: 401, data: { detail: 'email_not_verified' }, config });
        if (failure) throw new axios.AxiosError('failure', undefined, config, {}, { status: failure, data: { detail: 'verification_invalid' }, config });
        return { data: loginFailure ? { google: false, github: false } : { detail: 'Pokud účet čeká na ověření, odešleme zprávu.' }, config, status: 200, headers: {}, statusText: 'OK' };
    };
    try {
        const entry = resolve(dir, 'entry.jsx');
        await writeFile(entry, `export {default as Verify} from '../../src/pages/VerifyEmail.jsx';
export {AuthProvider} from '../../src/context/AuthContext.jsx';
export {default as Login} from '../../src/pages/login.jsx';`);
        const bundle = await build({ logLevel: 'silent', build: { write: false, minify: false,
            lib: { entry, formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|axios)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'bundle.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((p) => p.type === 'chunk' && p.isEntry).code);
        const { Verify, AuthProvider, Login } = await import(pathToFileURL(file).href);
        const render = async (path) => {
            if (root) await act(async () => root.unmount());
            window.history.replaceState({}, '', path);
            root = createRoot(document.getElementById('root'));
            await act(async () => root.render(React.createElement(React.StrictMode, null, React.createElement(Verify))));
        };
        sessionStorage.setItem('access_token', 'unrelated-existing-session');
        await render('/verify-email#token=secret-proof');
        assert.equal(window.location.hash, '');
        assert.equal(calls.length, 0);
        await act(async () => document.querySelector('button').click());
        assert.equal(calls.length, 1);
        assert.equal(calls[0].url, 'users/email/verification/confirm/');
        assert.deepEqual(JSON.parse(calls[0].data), { token: 'secret-proof' });
        assert.equal(calls[0].headers.Authorization, undefined);
        assert.match(document.querySelector('[role="status"]').textContent, /E-mail byl ověřen/);
        assert.equal(sessionStorage.getItem('access_token'), 'unrelated-existing-session');
        assert.equal(sessionStorage.getItem('refresh_token'), null);
        failure = 400;
        await render('/verify-email#token=expired-proof');
        await act(async () => document.querySelector('button').click());
        assert.match(document.querySelector('[role="alert"]').textContent, /Odkaz vypršel/);
        assert.ok(document.querySelector('input[type="email"]'));
        failure = 0;
        const field = document.querySelector('input');
        await act(async () => {
            Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(field, 'owner@example.test');
            field.dispatchEvent(new window.Event('input', { bubbles: true }));
        });
        await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
        assert.equal(calls.at(-1).url, 'users/email/verification/request/');
        assert.deepEqual(JSON.parse(calls.at(-1).data), { email: 'owner@example.test' });
        assert.equal(calls.at(-1).headers.Authorization, undefined);
        assert.equal(document.querySelector('button').disabled, true);
        const before = calls.length;
        await render('/verify-email');
        assert.equal(calls.length, before);
        assert.equal(document.querySelectorAll('input[type="email"]').length, 1);
        await act(async () => root.unmount());
        sessionStorage.clear();
        loginFailure = true;
        root = createRoot(document.getElementById('root'));
        await act(async () => root.render(React.createElement(AuthProvider, null, React.createElement(Login))));
        const fill = async (name, value) => act(async () => {
            const input = document.querySelector(`input[name="${name}"]`);
            Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
            input.dispatchEvent(new window.Event('input', { bubbles: true }));
        });
        await fill('username', 'pending');
        await fill('password', 'long-password');
        await act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
        assert.match(document.querySelector('[role="alert"]').textContent, /Nejdřív ověřte/);
        assert.ok(document.querySelector('input[type="email"]'));
        assert.equal(sessionStorage.getItem('access_token'), null);
    } finally {
        if (root) await act(async () => root.unmount());
        axios.defaults.adapter = previous;
        dom.window.close();
        // Resolve and check the target before a recursive Windows cleanup.
        const target = resolve(dir);
        assert.ok(target.startsWith(resolve('node_modules') + '\\') || target.startsWith(resolve('node_modules') + '/'));
        await rm(target, { recursive: true, force: true });
    }
});
