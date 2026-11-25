import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'vite';
import React, { act } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';

test('Home dashboard categorization, forms, refreshes, results and initial priorities', async (t) => {
    const dir = await mkdtemp(resolve('node_modules', '.home-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/', pretendToBeVisual: true });
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const { MemoryRouter } = await import('react-router-dom');
    const player = { id: 1, username: 'france', country: 'FRA', country_name: 'Francie' };
    const make = (id, status, extra = {}) => ({ id, name: `Game ${id}`, status, creator: 'france', players: [player],
        max_players: 7, is_public: true, movement_duration_minutes: 1440, retreat_duration_minutes: 720,
        adjustment_duration_minutes: 720, ...extra });
    const active = make(1, 'active', { current_phase: { season_name: 'Jaro', year: 1902, phase_type_name: 'Pohyby', deadline: '2026-10-22T12:00:00Z' } });
    const waiting = make(2, 'waiting', { is_public: false, invite_code: 'private-code' });
    const solo = make(3, 'finished', { result_type: 'solo', winner: player, finished_at: '2026-10-19T12:00:00Z' });
    const draw = make(4, 'finished', { result_type: 'draw', draw_participants: [player, { country_name: 'Anglie' }], finished_at: '2026-10-20T12:00:00Z' });
    const publicGame = make(5, 'waiting', { creator: 'other', players: [], invite_code: 'must-not-be-shown' });
    let own = [active, waiting, solo, draw], joinable = [publicGame], failCreate = false, createGate = null, createDetail = '';
    const calls = [];
    const preferences = Object.fromEntries(['email_phase_started', 'email_deadline_reminder', 'email_chat_message', 'email_draw_events', 'email_game_finished'].map((field) => [field, true]));
    globalThis.__homeTest = { logout() {}, api: {
        async get(url) {
            calls.push(['GET', url]);
            if (url === 'games/') return { data: [...own] };
            if (url === 'games/public/') return { data: [...joinable] };
            if (url === 'notifications/preferences/') return { data: preferences };
            throw new Error(url);
        },
        async post(url, payload) {
            calls.push(['POST', url, payload]);
            if (url === 'games/5/join/') { own = [...own, { ...publicGame, players: [player] }]; joinable = []; }
            else if (url === 'games/join-by-code/') own = [...own, make(6, 'waiting', { is_public: false, invite_code: payload.invite_code })];
            else if (url === 'games/') {
                if (createGate) await createGate;
                if (createDetail) throw { response: { status: 429, data: { detail: createDetail } } };
                if (failCreate) throw { response: { data: { name: ['Tento název nelze použít.'] } } };
                own = [...own, make(Math.max(...own.map((game) => game.id), 0) + 1, 'waiting', { ...payload, invite_code: 'created-private-code' })];
            } else throw new Error(url);
            return { data: {} };
        },
        async patch(url, payload) { calls.push(['PATCH', url, payload]); return { data: payload }; },
    } };
    let root;
    const originalError = console.error;
    try {
        const entry = resolve(dir, 'entry.jsx');
        await writeFile(entry, 'export { default } from "../../src/pages/home.jsx"; export { default as GameStatusBadge } from "../../src/components/game/GameStatusBadge.jsx"; export { default as formatDuration } from "../../src/components/game/formatDuration.js";');
        const bundle = await build({ logLevel: 'silent', plugins: [{ name: 'home-boundaries', enforce: 'pre', load(id) {
            const path = id.replaceAll('\\', '/');
            if (path.endsWith('/services/api.js')) return 'export default globalThis.__homeTest.api;';
            if (path.endsWith('/context/AuthContext.jsx')) return 'export const useAuth = () => ({user: {username: "france"}, logout: globalThis.__homeTest.logout});';
        } }], build: { write: false, minify: false, lib: { entry, formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|react-router-dom)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'home.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { default: Home, GameStatusBadge, formatDuration } = await import(pathToFileURL(file).href);
        root = createRoot(document.getElementById('root'));
        let key = 0;
        const render = () => act(async () => root.render(React.createElement(MemoryRouter, null, React.createElement(Home, { key: ++key }))));
        const tab = (id) => document.getElementById(`home-tab-${id}`);
        const panel = (id) => document.getElementById(`home-panel-${id}`);
        const click = (node) => act(async () => node.dispatchEvent(new window.MouseEvent('click', { bubbles: true })));
        const submit = (form) => act(async () => form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
        const input = async (id, value) => act(async () => {
            const node = document.getElementById(id);
            Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(node, value);
            node.dispatchEvent(new window.Event('input', { bubbles: true }));
        });
        const select = async (id, value) => act(async () => {
            const node = document.getElementById(id); node.value = value;
            node.dispatchEvent(new window.Event('change', { bubbles: true }));
        });
        const gameGets = () => calls.filter(([method, url]) => method === 'GET' && url.startsWith('games/')).length;
        await render();
        await t.test('owned tabs and separate public section, cards, keyboard navigation and no tab fetches', async () => {
            assert.equal(document.querySelectorAll('[role=tab]').length, 3);
            const navbar = document.querySelector('.dashboard-navbar');
            assert.match(navbar.textContent, /Diplomacie/);
            assert.match(navbar.textContent, /france/);
            assert.equal(navbar.querySelector('button').textContent, 'Odhlásit se');
            assert.ok(navbar.querySelector('img'));
            assert.equal(document.querySelector('h1').textContent, 'Moje hry');
            const grid = document.querySelector('.dashboard-main-grid');
            assert.deepEqual([...grid.children].map((node) => node.className), ['dashboard-owned', 'dashboard-quick-actions']);
            assert.equal(grid.nextElementSibling.className, 'dashboard-public');
            assert.equal(document.querySelectorAll('#game-name').length, 1);
            assert.equal(document.querySelectorAll('#invite-code').length, 1);
            assert.ok(grid.children[1].querySelector('.notification-settings'));
            assert.equal(panel('join').querySelector('code'), null);
            assert.equal(tab('active').getAttribute('aria-selected'), 'true');
            for (const [id, count, names] of [['active', 1, ['Game 1']], ['waiting', 1, ['Game 2']], ['finished', 2, ['Game 4', 'Game 3']]]) {
                assert.match(tab(id).textContent, new RegExp(`\\(${count}\\)`));
                assert.deepEqual([...panel(id).querySelectorAll('h3')].map((node) => node.textContent), names);
            }
            assert.match(panel('active').textContent, /Francie/);
            assert.match(panel('active').textContent, /Jaro 1902/);
            assert.match(panel('active').textContent, /Deadline/);
            assert.equal(panel('active').querySelector('a').getAttribute('href'), '/games/1');
            assert.match(panel('waiting').textContent, /24 hodin/);
            assert.match(panel('join').textContent, /Game 5/);
            assert.equal(panel('join').closest('section').getAttribute('aria-labelledby'), 'public-games-title');
            assert.equal(panel('join').querySelector('a'), null);
            assert.equal(gameGets(), 2);
            assert.equal(panel('waiting').querySelector('code').textContent, 'private-code');
            assert.match(panel('finished').textContent, /Vítěz: Francie — france/);
            assert.match(panel('finished').textContent, /Sdílené vítězství: Francie, Anglie/);
            const before = gameGets();
            await click(tab('finished')); await click(tab('waiting')); await click(tab('active'));
            await act(async () => tab('active').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })));
            assert.equal(document.activeElement, tab('waiting'));
            assert.equal(tab('waiting').getAttribute('aria-selected'), 'true');
            assert.equal(gameGets(), before);
        });
        await t.test('public join reloads both lists and preserves owned tab', async () => {
            const before = gameGets();
            await click(panel('join').querySelector('button'));
            assert.ok(calls.some(([method, url]) => method === 'POST' && url === 'games/5/join/'));
            assert.equal(gameGets() - before, 2);
            assert.equal(tab('waiting').getAttribute('aria-selected'), 'true');
            assert.match(panel('join').textContent, /Momentálně nejsou žádné veřejné hry/);
            assert.match(panel('waiting').textContent, /Game 5/);
        });
        await t.test('private invite, complete creation form, errors and notification preferences preserved', async () => {
            await input('invite-code', '  invite-test  ');
            await submit(document.getElementById('invite-code').closest('form'));
            assert.deepEqual(calls.find(([, url]) => url === 'games/join-by-code/')[2], { invite_code: 'invite-test' });
            assert.equal(document.getElementById('invite-code').value, '');
            assert.match(panel('waiting').textContent, /Game 6/);
            await input('game-name', 'Private creation');
            await select('max-players', '3'); await select('visibility', 'false');
            await select('movement_duration_minutes', '360'); await select('retreat_duration_minutes', '60'); await select('adjustment_duration_minutes', '1440');
            const form = document.getElementById('game-name').closest('form');
            failCreate = true;
            console.error = () => {};
            await submit(form);
            console.error = originalError;
            assert.ok(form.closest('details').open);
            assert.match(document.querySelector('[role="alert"]').textContent, /Název hry: Tento název/);
            failCreate = false;
            await submit(form);
            assert.deepEqual(calls.filter(([method, url]) => method === 'POST' && url === 'games/').at(-1)[2], {
                name: 'Private creation', max_players: 3, is_public: false,
                movement_duration_minutes: 360, retreat_duration_minutes: 60, adjustment_duration_minutes: 1440,
            });
            assert.match(panel('waiting').textContent, /created-private-code/);
            await input('game-name', 'Public creation');
            await submit(form);
            assert.equal(calls.filter(([method, url]) => method === 'POST' && url === 'games/').at(-1)[2].is_public, true);
            await submit(document.querySelector('.notification-settings form'));
            assert.ok(calls.some(([method, url]) => method === 'PATCH' && url === 'notifications/preferences/'));
        });
        await t.test('status badges and duration formatting', () => {
            for (const [status, emoji, label] of [['waiting', '⏳', 'Čeká'], ['active', '⚔️', 'Probíhá'], ['finished', '✅', 'Dokončeno'], ['future', '❔', 'Neznámý stav'], ['__proto__', '❔', 'Neznámý stav']]) {
                const markup = renderToStaticMarkup(React.createElement(GameStatusBadge, { status }));
                assert.ok(markup.includes(emoji));
                assert.ok(markup.includes(label));
            }
            for (const [minutes, label] of [[60, '1 hodina'], [120, '2 hodiny'], [360, '6 hodin'], [720, '12 hodin'], [1440, '24 hodin'], [2880, '48 hodin'], [4320, '72 hodin'], [90, '90 min'], [null, '—']]) {
                assert.equal(formatDuration(minutes), label);
            }
        });
        await t.test('creation blocks duplicate in-flight submits and displays backend limits', async () => {
            const field=document.getElementById('game-name');
            assert.equal(field.maxLength,100);
            await input('game-name','One request');
            const form=field.closest('form');
            let release;
            createGate=new Promise((resolve)=>{release=resolve;});
            const before=calls.filter(([method,url])=>method==='POST' && url==='games/').length;
            await submit(form);
            assert.equal(form.querySelector('button[type="submit"]').disabled,true);
            await submit(form);
            assert.equal(calls.filter(([method,url])=>method==='POST' && url==='games/').length,before+1);
            await act(async()=>release());
            createGate=null;
            assert.equal(form.querySelector('button[type="submit"]').disabled,false);
            await input('game-name','Too soon');
            createDetail='Další hru zatím nelze vytvořit. Počkejte 10 sekund.';
            console.error=()=>{};
            await submit(form);
            console.error=originalError;
            assert.match(document.querySelector('[role="alert"]').textContent,/Počkejte 10 sekund/);
            assert.equal(field.value,'Too soon');
            assert.equal(form.querySelector('button[type="submit"]').disabled,false);
            createDetail='';
        });
        await t.test('initial priority and all empty states', async () => {
            for (const [games, publicGames, expected] of [[[waiting, solo], [publicGame], 'waiting'], [[solo], [publicGame], 'finished'], [[solo], [], 'finished'], [[], [], 'finished']]) {
                own = games; joinable = publicGames;
                await render();
                assert.equal(tab(expected).getAttribute('aria-selected'), 'true');
            }
            assert.ok(panel('join').querySelector('.home-empty-state'));
            for (const id of ['active', 'waiting', 'finished']) {
                await click(tab(id));
                assert.ok(panel(id).querySelector('.home-empty-state'));
                assert.equal(panel(id).hidden, false);
            }
        });
    } finally {
        console.error = originalError;
        if (root) await act(async () => root.unmount());
        delete globalThis.__homeTest;
        dom.window.close();
        assert.ok(dir.startsWith(resolve('node_modules') + sep));
        await rm(dir, { recursive: true, force: true });
    }
});
