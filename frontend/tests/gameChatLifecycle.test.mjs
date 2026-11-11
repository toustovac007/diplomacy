import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm, readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { resolve, sep } from 'node:path';
import { JSDOM } from 'jsdom';
import { build } from 'vite';
import React, { act } from 'react';

// Render the real page/chat/draw/history components. Only network/auth and the
// unrelated SVG loader are replaced; clicks use the real resolve/loadGame path.
test('one chat and polling owner survives phase transitions and navigation', async () => {
    const dir = await mkdtemp(resolve('node_modules', '.chat-test-'));
    const diagnostics = [];
    const warnings = [];
    const originalLog = console.log;
    const originalError = console.error;
    const originalInterval = globalThis.setInterval;
    const originalClear = globalThis.clearInterval;
    const timers = new Map();
    let timerId = 0;
    let root;
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/games/1', pretendToBeVisual: true });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const { MemoryRouter, Routes, Route, Link } = await import('react-router-dom');
    globalThis.setInterval = (callback, ms) => { timers.set(++timerId, { callback, ms }); return timerId; };
    globalThis.clearInterval = (id) => timers.delete(id);
    const player = { id: 1, username: 'france', country: 'FRA', country_name: 'Francie' };
    let phase = 1;
    let finished = false;
    let waiting = false;
    let proposal = null;
    let unread = 3;
    const requests = [];
    const game = () => ({ id: 1, name: 'Lifecycle regression', creator: 'france', status: waiting ? 'waiting' : finished ? 'finished' : 'active',
        manual_resolve_allowed: true, players: [player], units: [], supply_centers: [], max_players: 7,
        current_phase: finished ? null : { id: phase, sequence: phase, year: 1901, season: 'spring', season_name: 'Jaro', phase_type: 'movement', phase_type_name: 'Pohyby', status: 'open' } });
    globalThis.__chatTest = {
        user: { username: 'france' },
        record: (...entry) => diagnostics.push(entry),
        api: {
            async get(url) {
                requests.push(url);
                if (url === 'games/1/') return { data: game() };
                if (url.endsWith('/readiness/')) return { data: { game_status: finished ? 'finished' : 'active', phase: finished ? null : { id: phase }, readiness_supported: true, is_required: false, is_ready: false, ready_count: 0, required_count: 0 } };
                if (url.endsWith('/chats/')) return { data: [{ id: 1, conversation_type: 'direct', participants: [player, { id: 2, username: 'england', country_name: 'Anglie' }], unread_count: unread }] };
                if (url.endsWith('/messages/')) return { data: { results: [{ id: 1, sender: 2, sender_username: 'england',
                    text: '<script>alert(1)</script>', created_at: '2026-01-01T12:00:00Z' }], next: null } };
                if (url.includes('draw-proposals')) return { data: { game_status: finished ? 'finished' : 'active', proposal, surviving_players: [] } };
                if (url.endsWith('/history/')) return { data: { phases: [{ id: 99, season_name: 'Podzim', year: 1900, phase_type_name: 'Pohyby' }] } };
                if (url.endsWith('/history/99/')) return { data: { phase: { id: 99, season_name: 'Podzim', year: 1900, phase_type_name: 'Pohyby' }, orders: [], orders_available: true, state_available: false } };
                if (url === 'orders/games/1/') return { data: [] };
                throw new Error(`Unexpected GET ${url}`);
            },
            async post(url) {
                requests.push(url);
                if (url === 'orders/games/1/resolve/') phase += 1;
                else if (url.endsWith('/read/')) unread = 0;
                else if (!url.endsWith('/read/')) throw new Error(`Unexpected POST ${url}`);
                return { data: {} };
            },
        },
    };
    try {
        const bundle = await build({ logLevel: 'silent', plugins: [{
            name: 'chat-test-boundaries', enforce: 'pre',
            async load(id) {
                const path = id.replaceAll('\\', '/');
                if (path.endsWith('/services/api.js')) return 'export default globalThis.__chatTest.api;';
                if (path.endsWith('/context/AuthContext.jsx')) return 'export const useAuth = () => ({ user: globalThis.__chatTest.user });';
                if (path.endsWith('/GameMap.jsx')) return 'export default function GameMap() { return null; }';
                for (const name of ['GameDetail', 'GameChat']) {
                    if (path.toLowerCase().endsWith(`/${name.toLowerCase()}.jsx`)) {
                        const source = await readFile(id, "utf8");
                        const signature = source.match(new RegExp('function ' + name + '\\([^]*?\\) \\{'))[0];
                        return source.replace(signature, `${signature}\nuseEffect(() => { const id = crypto.randomUUID(); globalThis.__chatTest.record('${name}', 'MOUNT', id); return () => globalThis.__chatTest.record('${name}', 'UNMOUNT', id); }, []);`);
                    }
                }
            },
        }], build: { write: false, minify: false, lib: { entry: resolve('src/pages/gameDetail.jsx'), formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|react-router-dom)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'page.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { default: GameDetail } = await import(pathToFileURL(file).href);
        console.log = () => {};
        console.error = (...args) => warnings.push(args.join(' '));
        const h = React.createElement;
        root = createRoot(document.getElementById('root'));
        await act(async () => root.render(h(React.StrictMode, null, h(MemoryRouter, { initialEntries: ['/games/1'] },
            h(Routes, null, h(Route, { path: '/games/:gameId', element: h(GameDetail) }),
                h(Route, { path: '/', element: h(Link, { to: '/games/1' }, 'Return to game') }))))));
        const click = async (text) => {
            const button = [...document.querySelectorAll('button,a')].find((node) => !node.closest('[hidden]') && node.textContent.includes(text));
            assert.ok(button, `Missing control ${text}`);
            await act(async () => button.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true })));
        };
        const counts = [document.querySelectorAll('.game-chat').length];
        const tab = (name) => [...document.querySelectorAll('[role="tab"]')].find((node) => node.textContent.startsWith(name));
        const panel = (name) => document.getElementById(tab(name).getAttribute('aria-controls'));
        assert.equal(tab('Hra').getAttribute('aria-selected'), 'true');
        assert.equal(panel('Diplomacie').hidden, true);
        assert.equal(document.querySelector('.tab-badge').textContent, '3');
        const chatMounts = () => diagnostics.filter((e) => e[0] === 'GameChat' && e[1] === 'MOUNT').length;
        const chatMountCount = chatMounts();
        await click('Diplomacie');
        assert.equal(panel('Diplomacie').hidden, false);
        await click('Anglie');
        assert.match(document.querySelector('.chat-history').textContent, /<script>alert\(1\)<\/script>/);
        assert.equal(document.querySelector('.game-chat script'), null);
        const textarea = document.querySelector('.chat-compose textarea');
        await act(async () => {
            Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set.call(textarea, 'Unsent draft');
            textarea.dispatchEvent(new window.Event('input', { bubbles: true }));
        });
        assert.match(document.querySelector('.chat-compose span').textContent, /12 \/ 4000/);
        assert.equal(document.querySelector('.tab-badge'), null);
        await click('Hra');
        unread = 4;
        const hiddenRequests = requests.length;
        await act(async () => { for (const timer of timers.values()) timer.callback(); });
        assert.equal(requests.slice(hiddenRequests).filter((url) => url.endsWith('/read/')).length, 0);
        assert.equal(document.querySelector('.tab-badge').textContent, '4');
        await click('Diplomacie');
        assert.equal(document.querySelector('.chat-compose textarea'), textarea);
        assert.equal(textarea.value, 'Unsent draft');
        await click('Historie');
        assert.equal(panel('Historie').hidden, false);
        assert.match(panel('Historie').textContent, /Podzim 1900/);
        assert.equal([...panel('Historie').querySelectorAll('button')].some((button) => button.textContent === 'Historie hry'), false);
        const gameRequests = requests.filter((url) => url === 'games/1/').length;
        await click('Hra');
        await click('Diplomacie');
        await click('Hra');
        assert.equal(requests.filter((url) => url === 'games/1/').length, gameRequests);
        assert.equal(chatMounts(), chatMountCount);
        assert.equal(document.querySelectorAll('.game-chat').length, 1);
        // The same chat/draft and timers survive repeated focus entry/exit.
        document.body.style.overflow = 'auto';
        document.documentElement.style.overflow = 'scroll';
        const focusEntry = [...document.querySelectorAll('button')].find((node) => node.textContent === 'Mapa na celou obrazovku');
        await click('Mapa na celou obrazovku');
        assert.equal(document.querySelector('[role="dialog"]').getAttribute('aria-modal'), 'true');
        assert.equal(document.activeElement.textContent, 'Ukončit herní režim');
        assert.equal(panel('Diplomacie').hidden, false);
        assert.equal(document.querySelector('.chat-compose textarea'), textarea);
        assert.equal(textarea.value, 'Unsent draft');
        assert.equal(document.querySelectorAll('.game-chat').length, 1);
        assert.equal(document.body.style.overflow, 'hidden');
        await click('Ukončit herní režim');
        assert.equal(document.querySelector('[role="dialog"]'), null);
        assert.equal(document.activeElement, focusEntry);
        assert.equal(document.body.style.overflow, 'auto');
        assert.equal(document.documentElement.style.overflow, 'scroll');
        assert.equal(tab('Hra').getAttribute('aria-selected'), 'true');
        assert.equal(panel('Diplomacie').hidden, true);
        await click('Mapa na celou obrazovku');
        await act(async () => document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
        assert.equal(document.querySelector('[role="dialog"]'), null);
        await click('Diplomacie');
        assert.equal(document.querySelector('.chat-compose textarea'), textarea);
        assert.equal(textarea.value, 'Unsent draft');
        await click('Hra');
        assert.equal(chatMounts(), chatMountCount);
        const other = { id: 2, username: 'england', country_name: 'Anglie' };
        await act(async () => {
            tab('Hra').focus();
            tab('Hra').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
        });
        assert.equal(document.activeElement, tab('Diplomacie'));
        assert.equal(tab('Diplomacie').getAttribute('aria-selected'), 'true');
        await act(async () => tab('Diplomacie').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Home', bubbles: true })));
        assert.equal(document.activeElement, tab('Hra'));
        assert.equal(tab('Hra').getAttribute('aria-selected'), 'true');
        proposal = { id: 1, status: 'open', proposer: player, participants: [player, other], voters: [{ player, vote: 'accept' }, { player: other, vote: null }] };
        await act(async () => { for (const timer of timers.values()) if (timer.ms === 10000) timer.callback(); });
        const drawButtons = () => [...document.querySelectorAll('.draw-actions button')].map((node) => node.textContent);
        assert.deepEqual(drawButtons(), ['Zrušit návrh']);
        assert.match(document.querySelector('.draw-panel').textContent, /souhlasí/);
        proposal = { ...proposal, proposer: other };
        await act(async () => { for (const timer of timers.values()) if (timer.ms === 10000) timer.callback(); });
        assert.deepEqual(drawButtons(), ['Souhlasím', 'Nesouhlasím']);
        proposal = null;
        const initialMounts = diagnostics.filter((e) => e[1] === 'MOUNT').length;
        for (let i = 0; i < 3; i++) {
            await click('Vyhodnotit fázi nyní');
            counts.push(document.querySelectorAll('.game-chat').length);
        }
        originalLog('Phase DOM counts:', counts, 'root children:', document.querySelector('#root').children.length);
        originalLog('Mount/unmount diagnostics:', JSON.stringify(diagnostics));
        originalLog('Active polling timers:', [...timers.values()].map((t) => t.ms));
        originalLog('Duplicate key warnings:', warnings.filter((w) => w.includes('same key')).length);
        assert.deepEqual(counts, [1, 1, 1, 1]);
        assert.equal(diagnostics.filter((e) => e[1] === 'MOUNT').length, initialMounts);
        assert.equal(document.querySelector('#root').children.length, 1);
        const before = requests.length;
        await act(async () => { for (const timer of timers.values()) timer.callback(); });
        assert.equal(requests.slice(before).filter((url) => url.endsWith('/chats/')).length, 1);
        assert.equal(requests.slice(before).filter((url) => url.endsWith('/messages/')).length, 1);
        assert.equal([...timers.values()].filter((timer) => timer.ms === 5000).length, 1);
        assert.equal([...timers.values()].filter((timer) => timer.ms === 10000).length, 3); // chat + draw + readiness
        await click('Mapa na celou obrazovku');
        finished = true;
        await act(async () => { for (const timer of timers.values()) timer.callback(); });
        assert.equal(document.querySelectorAll('.game-chat').length, 1);
        assert.equal(document.querySelector('[role="dialog"]'), null);
        assert.equal(document.body.style.overflow, 'auto');
        assert.equal([...document.querySelectorAll('button')].some((node) => node.textContent === 'Mapa na celou obrazovku'), false);
        assert.match(document.querySelector('.game-chat').textContent, /pouze ke čtení/);
        assert.equal(document.querySelector('.chat-compose'), null);
        assert.equal(tab('Výsledek').getAttribute('aria-selected'), 'true');
        assert.equal(panel('Diplomacie').hidden, true);
        await click('Diplomacie');
        assert.equal(panel('Diplomacie').hidden, false);
        assert.equal(chatMounts(), chatMountCount);
        await click('Zpět na moje hry');
        assert.equal(document.querySelectorAll('.game-chat').length, 0);
        assert.equal(timers.size, 0);
        await click('Return to game');
        assert.equal(document.querySelectorAll('.game-chat').length, 1);
        assert.equal(tab('Výsledek').getAttribute('aria-selected'), 'true');
        await click('Zpět na moje hry');
        finished = false; waiting = true;
        await click('Return to game');
        assert.equal(document.querySelector('[role=tablist]'), null);
        assert.equal(document.querySelector('.game-chat'), null);
        assert.match(document.body.textContent, /Lobby/);
        assert.equal([...document.querySelectorAll('button')].some((node) => node.textContent === 'Mapa na celou obrazovku'), false);
        assert.equal(warnings.filter((w) => w.includes('same key')).length, 0);
    } finally {
        if (root) await act(async () => root.unmount());
        console.log = originalLog;
        console.error = originalError;
        globalThis.setInterval = originalInterval;
        globalThis.clearInterval = originalClear;
        delete globalThis.__chatTest;
        dom.window.close();
        assert.ok(dir.startsWith(resolve("node_modules") + sep));
        await rm(dir, { recursive: true, force: true });
    }
});

