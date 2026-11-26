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
    const { MemoryRouter, Routes, Route, useNavigate } = await import('react-router-dom');
    function HistoryNavigation() {
        const navigate = useNavigate();
        return React.createElement(React.Fragment, null,
            React.createElement('button', {'data-history':'back', onClick:()=>navigate(-1)}, 'Test back'),
            React.createElement('button', {'data-history':'forward', onClick:()=>navigate(1)}, 'Test forward'));
    }
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
    let wallet = {available: 1000, frozen: 200, total: 1200, minimum: 300, refill_due_at: null};
    let nextWallet;
    const preferences = Object.fromEntries(['email_phase_started', 'email_deadline_reminder', 'email_chat_message', 'email_draw_events', 'email_game_finished'].map((field) => [field, true]));
    globalThis.__homeTest = { logout() {}, api: {
        async get(url) {
            calls.push(['GET', url]);
            if (url === 'games/') return { data: [...own] };
            if (url === 'games/public/') return { data: [...joinable] };
            if (url === 'users/tokens/') return { data: {...wallet} };
            if (url === 'users/ranking/') return { data: [
                {rank: 1, username: 'england', available: 200, frozen: 1800, total: 2000},
                {rank: 2, username: 'france', available: 700, frozen: 300, total: 1000},
            ] };
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
                if (nextWallet) { wallet = nextWallet; nextWallet = null; }
            } else throw new Error(url);
            return { data: {} };
        },
        async patch(url, payload) { calls.push(['PATCH', url, payload]); return { data: payload }; },
    } };
    let root;
    const originalError = console.error;
    try {
        const entry = resolve(dir, 'entry.jsx');
        await writeFile(entry, 'export { default } from "../../src/pages/home.jsx"; export { default as GameStatusBadge } from "../../src/components/game/GameStatusBadge.jsx"; export { default as formatDuration } from "../../src/components/game/formatDuration.js"; export { default as Ranking } from "../../src/pages/Ranking.jsx"; export { refillWait } from "../../src/components/tokens/tokenRules.js";');
        const bundle = await build({ logLevel: 'silent', plugins: [{ name: 'home-boundaries', enforce: 'pre', load(id) {
            const path = id.replaceAll('\\', '/');
            if (path.endsWith('/services/api.js')) return 'export default globalThis.__homeTest.api; export const getSessionVersion = () => 1;';
            if (path.endsWith('/context/AuthContext.jsx')) return 'export const useAuth = () => ({user: {username: "france"}, logout: globalThis.__homeTest.logout});';
        } }], build: { write: false, minify: false, lib: { entry, formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|react-router-dom)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'home.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { default: Home, GameStatusBadge, formatDuration, Ranking, refillWait } = await import(pathToFileURL(file).href);
        root = createRoot(document.getElementById('root'));
        let key = 0;
        const render = (entry = '/') => act(async () => root.render(React.createElement(MemoryRouter, { key: ++key, initialEntries: [entry] },
            React.createElement(Routes, null,
                React.createElement(Route, {path:'/', element:React.createElement(Home)}),
                React.createElement(Route, {path:'/ranking', element:React.createElement(Ranking)})),
            React.createElement(HistoryNavigation))));
        const tab = (id) => document.getElementById(`home-nav-${id}`);
        const panel = (id) => document.getElementById(`home-panel-${id}`);
        const click = (node) => act(async () => node.dispatchEvent(new window.MouseEvent('click', { bubbles: true, cancelable: true })));
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
        await t.test('five navbar views, separate public view, keyboard navigation and no filter fetches', async () => {
            assert.equal(document.querySelectorAll('[role=tab]').length, 0);
            assert.deepEqual([...document.querySelectorAll('.dashboard-navigation a')].map(node => node.textContent), ['Aktivní', 'Čekající', 'Dokončené', 'Veřejné hry', 'Žebříček']);
            assert.equal(document.querySelectorAll('.dashboard-navigation [aria-current=page]').length, 1);
            const navbar = document.querySelector('.dashboard-navbar');
            assert.match(navbar.textContent, /Diplomacie/);
            assert.match(navbar.textContent, /france/);
            assert.equal(navbar.querySelector('button').textContent, 'Odhlásit se');
            assert.ok(navbar.querySelector('img'));
            assert.equal(navbar.querySelector('.dashboard-brand img').getAttribute('src'), '/diplomacie-mark.svg');
            assert.equal(document.querySelector('h1').textContent, 'Aktivní hry');
            const grid = document.querySelector('.dashboard-main-grid');
            assert.deepEqual([...grid.children].map((node) => node.className), ['dashboard-owned', 'dashboard-quick-actions']);
            assert.equal(grid.nextElementSibling, null);
            assert.equal(document.querySelector('.dashboard-public'), null);
            assert.ok(grid.children[0].contains(panel('public')));
            assert.equal(panel('public').hidden, true);
            assert.equal(document.querySelectorAll('#game-name').length, 1);
            assert.equal(document.querySelectorAll('#invite-code').length, 1);
            assert.ok(grid.children[1].querySelector('.notification-settings'));
            assert.equal(panel('public').querySelector('code'), null);
            assert.equal(tab('active').getAttribute('aria-current'), 'page');
            for (const [id, count, names] of [['active', 1, ['Game 1']], ['waiting', 1, ['Game 2']], ['finished', 2, ['Game 4', 'Game 3']]]) {
                assert.equal(panel(id).querySelectorAll('.home-game-card').length, count);
                assert.deepEqual([...panel(id).querySelectorAll('h3')].map((node) => node.textContent), names);
            }
            assert.match(panel('active').textContent, /Francie/);
            assert.match(panel('active').textContent, /Jaro 1902/);
            assert.match(panel('active').textContent, /Deadline/);
            assert.equal(panel('active').querySelector('a').getAttribute('href'), '/games/1');
            assert.match(panel('waiting').textContent, /24 hodin/);
            assert.match(panel('public').textContent, /Game 5/);
            assert.equal(panel('public').getAttribute('aria-labelledby'), 'home-nav-public');
            assert.equal(panel('public').querySelector('a'), null);
            assert.equal(gameGets(), 2);
            assert.equal(panel('waiting').querySelector('code').textContent, 'private-code');
            assert.match(panel('finished').textContent, /Vítěz: Francie — france/);
            assert.match(panel('finished').textContent, /Sdílené vítězství: Francie, Anglie/);
            const before = gameGets();
            await click(tab('finished')); await click(tab('waiting')); await click(tab('active'));
            await act(async () => tab('active').dispatchEvent(new window.KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true })));
            assert.equal(document.activeElement, tab('waiting'));
            assert.equal(tab('waiting').getAttribute('aria-current'), 'page');
            assert.equal(gameGets(), before);
        });
        await t.test('all five views and browser history preserve quick-action drafts without game refetches', async () => {
            const before = gameGets();
            const form = document.getElementById('game-name').closest('form');
            form.closest('details').open = true;
            await input('game-name', 'Rozpracovaná hra');
            await input('invite-code', 'draft-invitation');
            await select('max-players', '3');
            await click(tab('public'));
            await click(tab('ranking'));
            assert.equal(document.querySelector('h1').textContent, 'Žebříček hráčů');
            assert.ok(document.querySelector('.token-ranking'));
            assert.equal(document.getElementById('game-name').closest('form'), form);
            assert.equal(form.closest('details').open, true);
            await click(document.querySelector('[data-history=back]'));
            assert.equal(tab('public').getAttribute('aria-current'), 'page');
            await click(document.querySelector('[data-history=forward]'));
            assert.equal(tab('ranking').getAttribute('aria-current'), 'page');
            for (const view of ['active', 'finished', 'waiting']) await click(tab(view));
            assert.equal(document.getElementById('game-name').value, 'Rozpracovaná hra');
            assert.equal(document.getElementById('invite-code').value, 'draft-invitation');
            assert.equal(document.getElementById('max-players').value, '3');
            assert.equal(document.getElementById('game-name').closest('form'), form);
            assert.equal(gameGets(), before);
            assert.equal(document.querySelectorAll('#game-name').length, 1);
            await input('game-name', ''); await input('invite-code', ''); await select('max-players', '7');
            form.closest('details').open = false;
        });
        await t.test('public join reloads both lists and preserves public view', async () => {
            await click(tab('public'));
            assert.equal(panel('public').hidden, false);
            assert.equal(panel('waiting').hidden, true);
            const before = gameGets();
            await click(panel('public').querySelector('button'));
            assert.ok(calls.some(([method, url]) => method === 'POST' && url === 'games/5/join/'));
            assert.equal(gameGets() - before, 2);
            assert.equal(tab('public').getAttribute('aria-current'), 'page');
            assert.match(panel('public').textContent, /Momentálně nejsou žádné veřejné hry/);
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
                token_stake: 100, scoring: 'dss',
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
                assert.equal(tab(expected).getAttribute('aria-current'), 'page');
            }
            assert.ok(panel('public').querySelector('.home-empty-state'));
            for (const id of ['active', 'waiting', 'finished']) {
                await click(tab(id));
                assert.ok(panel(id).querySelector('.home-empty-state'));
                assert.equal(panel(id).hidden, false);
            }
        });
        await t.test('direct URLs select the requested view and invalid values safely fall back', async () => {
            own = [active, waiting]; joinable = [publicGame];
            for (const [url, view] of [['/?view=active','active'], ['/?view=waiting','waiting'],
                ['/?view=finished','finished'], ['/?view=public','public'], ['/ranking','ranking'], ['/ranking/','ranking'],
                ['/?view=__proto__','active'], ['/?view=unknown','active']]) {
                await render(url);
                assert.equal(tab(view).getAttribute('aria-current'), 'page');
                assert.equal(panel(view).hidden, false);
                assert.equal(document.querySelectorAll('.dashboard-navigation [aria-current=page]').length, 1);
                for (const other of ['active','waiting','finished','public','ranking'].filter(id=>id!==view)) {
                    assert.equal(panel(other).hidden, true);
                }
            }
        });
        await t.test('wallet, affordable stake choices, scoring payload and refreshed balances', async () => {
            wallet = {available: 200, frozen: 100, total: 300, minimum: 300, refill_due_at: null};
            joinable = [make(99, 'waiting', {creator: 'other', token_stake: 500, scoring: 'sos', token_pot: 500})];
            await render();
            assert.match(document.querySelector('.token-wallet').textContent, /200Dostupné100Zmražené/);
            assert.ok(document.querySelector('.token-amount--frozen img'));
            assert.deepEqual([...document.getElementById('token-stake').options].map(option => Number(option.value)), [100, 200, 300, 500, 800, 1000, 1500]);
            assert.equal(document.querySelector('#token-stake option[value="500"]').disabled, true);
            assert.equal(panel('public').querySelector('button').disabled, true);
            const before = calls.filter(([method, url]) => method === 'POST' && url === 'games/').length;
            await input('game-name', 'Too expensive');
            await select('token-stake', '500');
            const form = document.getElementById('game-name').closest('form');
            assert.equal(form.querySelector('button[type="submit"]').disabled, true);
            await submit(form);
            assert.equal(calls.filter(([method, url]) => method === 'POST' && url === 'games/').length, before);
            await select('token-stake', '200');
            await select('scoring', 'sos');
            nextWallet = {available: 0, frozen: 300, total: 300, minimum: 300, refill_due_at: null};
            await submit(form);
            const payload = calls.filter(([method, url]) => method === 'POST' && url === 'games/').at(-1)[2];
            assert.equal(payload.token_stake, 200);
            assert.equal(payload.scoring, 'sos');
            assert.match(document.querySelector('.token-wallet').textContent, /0Dostupné300Zmražené/);
            assert.equal(form.querySelector('button[type="submit"]').disabled, true);
        });
        await t.test('minimum refill countdown, hourly delay, and top-ten ranking view', async () => {
            const due = Date.now() + 26 * 3_600_000;
            wallet = {available: 150, frozen: 100, total: 250, minimum: 300, refill_due_at: new Date(due).toISOString()};
            await render();
            assert.match(document.querySelector('.token-refill').textContent, /1 d 2 h/);
            assert.match(document.querySelector('.token-refill').textContent, /48 hodin/);
            assert.deepEqual(refillWait(new Date(due).toISOString(), due - 26 * 3_600_000), {days: 1, hours: 2, ready: false});
            wallet = {...wallet, refill_due_at: new Date(Date.now() - 1000).toISOString()};
            await act(async () => root.render(React.createElement(MemoryRouter, {key: 'ranking', initialEntries: ['/ranking']}, React.createElement(Ranking))));
            assert.equal(document.querySelector('h1').textContent, 'Žebříček hráčů');
            assert.match(document.querySelector('.token-refill').textContent, /hodinovou kontrolu/);
            const rows = document.querySelectorAll('.token-ranking tbody tr');
            assert.equal(rows.length, 2);
            assert.match(rows[0].textContent, /england/);
            assert.match(rows[1].textContent, /france \(Ty\)/);
            assert.equal(rows[1].className, 'ranking-current');
            assert.equal(document.querySelector('nav a[href="/ranking"]').getAttribute('aria-current'), 'page');
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
