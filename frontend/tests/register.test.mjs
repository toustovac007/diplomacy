import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import { build } from 'vite';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import axios from 'axios';

test('registration keeps validation and payload, then asks for verification without automatic login', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.register-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, Event: dom.window.Event,
        sessionStorage: dom.window.sessionStorage, localStorage: dom.window.localStorage, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const previous = axios.defaults.adapter;
    const calls = [];
    axios.defaults.adapter = async (config) => {
        calls.push(config);
        const data = config.url === 'token/' ? { access: 'test-access', refresh: 'test-refresh' }
            : config.url === 'users/me/' ? { username: 'france' } : {};
        return { data, config, status: 200, headers: {}, statusText: 'OK' };
    };
    let root;
    try {
        const entry = resolve(dir, 'entry.jsx');
        await writeFile(entry, `export {AuthProvider} from '../../src/context/AuthContext.jsx';
export {default as Register} from '../../src/pages/register.jsx';`);
        const bundle = await build({ logLevel: 'silent', build: { write: false, minify: false,
            lib: { entry, formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|axios)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'bundle.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((p) => p.type === 'chunk' && p.isEntry).code);
        const { AuthProvider, Register } = await import(pathToFileURL(file).href);
        let back = 0;
        root = createRoot(document.getElementById('root'));
        await act(async () => root.render(React.createElement(AuthProvider, null,
            React.createElement(Register, { onBackToLogin: () => back++ }))));
        assert.deepEqual([...document.querySelectorAll('input')].map((i) => i.name), ['username', 'email', 'password', 'passwordAgain']);
        for (const label of document.querySelectorAll('label')) assert.ok(label.control.required);
        assert.equal(document.querySelectorAll('.login-artwork[aria-hidden="true"] img[alt=""]').length, 2);
        assert.equal(document.querySelector('button[type="submit"]').textContent.trim(), 'Vytvořit účet');
        await act(async () => document.querySelector('button[type="button"]').click());
        assert.equal(back, 1);
        const fill = async (name, value) => act(async () => {
            const input = document.querySelector(`[name="${name}"]`);
            Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value);
            input.dispatchEvent(new window.Event('input', { bubbles: true }));
        });
        const submit = async () => act(async () => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
        await fill('username', 'france');
        await fill('email', 'france@example.test');
        await fill('password', 'long-test-password');
        await submit();
        assert.equal(document.querySelector('[role="alert"]').textContent, 'Hesla se neshodují.');
        assert.equal(calls.length, 0);
        await fill('password', 'short');
        await fill('passwordAgain', 'short');
        await submit();
        assert.equal(document.querySelector('[role="alert"]').textContent, 'Heslo musí mít alespoň 8 znaků.');
        assert.equal(calls.length, 0);
        await fill('password', 'long-test-password');
        await fill('passwordAgain', 'long-test-password');
        await submit();
        assert.deepEqual(calls.map((c) => c.url), ['users/register/']);
        assert.deepEqual(JSON.parse(calls[0].data), { username: 'france', email: 'france@example.test', password: 'long-test-password' });
        assert.equal(sessionStorage.getItem('access_token'), null);
        assert.equal(sessionStorage.getItem('refresh_token'), null);
        assert.equal(document.querySelector('h2').textContent, 'Ověřte svůj e-mail');
        assert.equal(document.querySelector('input[name="email"]').value, 'france@example.test');
    } finally {
        if (root) await act(async () => root.unmount());
        axios.defaults.adapter = previous;
        dom.window.close();
        await rm(dir, { recursive: true, force: true });
    }
});
