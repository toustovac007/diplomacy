import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'vite';
import React, { act } from 'react';

test('readiness locks real map/text/Winter controls and keeps chat alive across transitions', async () => {
    const css = await readFile(resolve('src/index.css'), 'utf8');
    assert.match(css, /\.game-secondary-panels\s*>\s*:only-child\s*\{\s*grid-column:\s*1\s*\/\s*-1\s*;/);
    const dir = await mkdtemp(resolve('node_modules', '.readiness-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost/games/1', pretendToBeVisual: true });
    const originals = { fetch: globalThis.fetch, setInterval: globalThis.setInterval, clearInterval: globalThis.clearInterval };
    Object.assign(globalThis, { window: dom.window, document: dom.window.document, DOMParser: dom.window.DOMParser,
        XMLSerializer: dom.window.XMLSerializer, IS_REACT_ACT_ENVIRONMENT: true });
    let mediaListener;
    window.matchMedia = () => ({ matches: false, addEventListener: (_, callback) => { mediaListener = callback; }, removeEventListener() {} });
    const { createRoot } = await import('react-dom/client');
    const { MemoryRouter, Routes, Route } = await import('react-router-dom');
    const svg = await readFile(resolve('public/maps/standard.svg'), 'utf8');
    globalThis.fetch = async () => ({ ok: true, text: async () => svg });
    let timerId = 0;
    const timers = new Map();
    globalThis.setInterval = (fn, ms) => { timers.set(++timerId, { fn, ms }); return timerId; };
    globalThis.clearInterval = (id) => timers.delete(id);
    const player = { id: 1, username: 'france', country: 'FRA', country_name: 'Francie' };
    const unit = { id: 1, country: 'FRA', owner_username: 'france', unit_type: 'army', province_code: 'PAR', province_name: 'Paříž', province_type: 'inland' };
    let phaseId = 1, phaseType = 'movement', ready = false, manual = false, lastReady = false;
    let disbands = 0, builds = 0, required = true, failPost = false;
    let pendingGet = null;
    const calls = [];
    const savedMovement = [{ id: 1, saved_unit_id: 1, unit: 1, order_type: 'move', origin: 'PAR', target_code: 'BUR', result: 'pending' }];
    const savedWinter = [{ id: 2, order_type: 'build', unit_type: 'army', province_code: 'MAR' }];
    const center = { code: 'BRE', name: 'Brest', army_allowed: true, fleet_allowed: true, fleet_coast_codes: [] };
    const status = () => ({ game_status: 'active', phase: { id: phaseId, phase_type: phaseType },
        readiness_supported: phaseType !== 'retreat', is_required: required, is_ready: ready,
        ready_count: ready ? 1 : 0, required_count: 3, missing_order_count: phaseType === 'movement' ? 1 : 0,
        builds_remaining: builds, disbands_remaining: disbands, phase_resolved: false });
    const gameName = 'Readiness UI with a very long game name '.repeat(12);
    const game = () => ({ id: 1, name: gameName, creator: 'france', status: 'active', manual_resolve_allowed: manual,
        players: [player], units: [{ ...unit, is_dislodged: phaseType === 'retreat' }], supply_centers: [{ province_code: 'PAR', owner_country: 'FRA' }],
        current_phase: { id: phaseId, sequence: phaseId, year: 1901, season: 'spring', season_name: 'Jaro', phase_type: phaseType, phase_type_name: phaseType, status: 'open' } });
    globalThis.__readinessTest = { api: {
        async get(url, config) {
            calls.push(['GET', url]);
            if (url === 'games/1/') return { data: game() };
            if (url.endsWith('/readiness/')) {
                if (pendingGet) await pendingGet;
                if (config?.signal.aborted) throw new Error('aborted');
                return { data: status() };
            }
            if (url.endsWith('/chats/')) return { data: [{ id: 1, conversation_type: 'public', participants: [player], unread_count: 0 }] };
            if (url.endsWith('/messages/')) return { data: { results: [], next: null } };
            if (url.includes('draw-proposals')) return { data: { game_status: 'active', proposal: null, surviving_players: [] } };
            if (url.endsWith('/adjustment-status/')) return { data: { delta: disbands ? -1 : 2, disband_count: 1, build_count: 2,
                disbands_remaining: disbands, builds_remaining: builds, buildable_home_centers: [center] } };
            if (url.endsWith('/adjustments/')) return { data: savedWinter };
            if (url.endsWith('/retreats/')) return { data: [] };
            if (url === 'orders/games/1/') return { data: savedMovement };
            throw new Error(`Unexpected GET ${url}`);
        },
        async post(url, payload) {
            calls.push(['POST', url, payload]);
            if (url.endsWith('/readiness/')) {
                if (failPost) throw { response: { data: { detail: 'Zkus to znovu.' } } };
                ready = payload.ready;
                const data = status();
                if (lastReady) { data.phase_resolved = true; phaseId++; ready = false; }
                return { data };
            }
            if (url.endsWith('/read/')) return { data: {} };
            if (url === 'orders/games/1/') {
                if (payload.target === 'MOS') throw { response: { data: { detail: 'Neplatný pohyb do MOS.' } } };
                return { data: { ...savedMovement[0], target_code: payload.target } };
            }
            throw new Error(`Unexpected POST ${url}`);
        },
    } };
    let root;
    try {
        const bundle = await build({ logLevel: 'silent', plugins: [{ name: 'readiness-network', enforce: 'pre', load(id) {
            const path = id.replaceAll('\\', '/');
            if (path.endsWith('/services/api.js')) return 'export default globalThis.__readinessTest.api;';
            if (path.endsWith('/context/AuthContext.jsx')) return 'export const useAuth = () => ({ user: {username: "france"} });';
        } }], build: { write: false, minify: false, lib: { entry: resolve('src/pages/gameDetail.jsx'), formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom|react-router-dom)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'page.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { default: Page } = await import(pathToFileURL(file).href);
        root = createRoot(document.getElementById('root'));
        const h = React.createElement;
        await act(async () => root.render(h(MemoryRouter, { initialEntries: ['/games/1'] }, h(Routes, null,
            h(Route, { path: '/games/:gameId', element: h(Page) })))));
        const button = (text) => [...document.querySelectorAll('button')].find((node) => !node.closest('[hidden]') && node.textContent.includes(text));
        const click = async (node) => { assert.ok(node); await act(async () => node.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))); };
        const poll = async () => { await act(async () => { for (const timer of [...timers.values()]) timer.fn(); }); };
        const mapClick = () => click(document.querySelector('#MouseLayer #par'));
        const countGets = () => calls.filter(([method, url]) => method === 'GET' && url === 'games/1/').length;
        const chat = document.querySelector('.game-chat');
        assert.ok(chat);
        assert.match(document.querySelector('.phase-readiness').textContent, /0 \/ 3 připraveno/);
        assert.match(document.querySelector('.phase-readiness').textContent, /HOLD/);
        assert.equal(button('Vyhodnotit fázi nyní'), undefined);
        const manualOrders = document.querySelector('.game-manual-orders');
        const allUnits = document.querySelector('.game-all-units');
        const secondaryPanels = document.querySelector('.game-secondary-panels');
        assert.ok(manualOrders);
        assert.ok(allUnits);
        assert.deepEqual([...secondaryPanels.children], [manualOrders, allUnits]);
        assert.ok(manualOrders.classList.contains('game-secondary-panel'));
        assert.ok(allUnits.classList.contains('game-secondary-panel'));
        assert.equal(manualOrders.open, false);
        assert.equal(allUnits.open, false);
        assert.match(manualOrders.querySelector('summary').textContent, /Ruční zadávání rozkazů \(1\)/);
        const manualForm = manualOrders.querySelector('form');
        const initialForms = manualOrders.innerHTML;
        const initialArrows = document.querySelector('#ReactOrderLayer').innerHTML;
        const initialCalls = calls.length;
        await click(manualOrders.querySelector('summary'));
        assert.equal(manualOrders.open, true);
        assert.equal(manualOrders.querySelector('form'), manualForm);
        await click(manualOrders.querySelector('summary'));
        assert.equal(manualOrders.open, false);
        assert.equal(manualOrders.innerHTML, initialForms);
        assert.equal(document.querySelector('#ReactOrderLayer').innerHTML, initialArrows);
        assert.equal(calls.length, initialCalls);
        await click(allUnits.querySelector('summary'));
        assert.equal(allUnits.open, true);
        assert.equal(manualOrders.open, false);
        assert.equal(allUnits.querySelectorAll('li').length, game().units.length);
        assert.match(allUnits.querySelector('li').textContent, /Paříž/);
        await click(allUnits.querySelector('summary'));
        assert.equal(allUnits.open, false);
        assert.equal(calls.length, initialCalls);
        assert.ok(document.querySelector('.game-map'));
        await mapClick();
        assert.ok(document.querySelector('#ReactOrderWheel'));
        const originalMap = document.querySelector('.game-map');
        const originalSvg = document.querySelector('.game-map svg');
        await click([...document.querySelectorAll('#ReactOrderWheel title')].find((node) => node.textContent === 'MOVE').parentElement);
        assert.match(document.querySelector('.focus-map-area').textContent, /Klikni na cílovou provincii/);
        await click(button('Mapa na celou obrazovku'));
        assert.equal(document.querySelectorAll('.game-map').length, 1);
        assert.equal(document.querySelector('.game-map'), originalMap);
        assert.match(document.querySelector('.focus-status-panel').textContent, /Klikni na cílovou provincii/);
        const assertStableMap = () => {
            assert.equal(document.querySelector('.game-map'), originalMap);
            assert.equal(document.querySelector('.game-map svg'), originalSvg);
            assert.equal(document.querySelectorAll('.game-map').length, 1);
            assert.equal(document.querySelectorAll('.game-chat').length, 1);
            assert.equal(document.querySelector('.game-chat'), chat);
            assert.deepEqual([...document.querySelector('.focus-map-area').children], [originalMap]);
            assert.doesNotMatch(document.querySelector('.focus-map-area').textContent,
                /Klikni na cílovou|Vybraná jednotka|Vybraný cíl|Neplatný pohyb|Rozkaz byl uložen/);
        };
        assertStableMap();
        assert.equal(document.querySelector('.game-map svg'), originalSvg);
        assert.equal(document.querySelector('.focus-title strong').title, gameName);
        assert.equal(manualOrders.closest('.game-secondary-panels').hidden, true);
        assert.equal(allUnits.closest('.game-secondary-panels').hidden, true);
        assert.ok(document.querySelector('#ReactOrderWheel'));
        await click(button('Ukončit herní režim'));
        assert.ok(document.querySelector('#ReactOrderWheel'));
        assert.equal(document.querySelector('.game-map'), originalMap);
        assert.equal(document.querySelector('.game-map svg'), originalSvg);
        assert.equal(manualOrders.closest('.game-secondary-panels').hidden, false);
        assert.equal(allUnits.closest('.game-secondary-panels').hidden, false);
        assert.equal(manualOrders.querySelector('form'), manualForm);
        assert.equal(manualOrders.innerHTML, initialForms);
        // Real map input still reaches the order API after entering focus mode.
        await click(button('Mapa na celou obrazovku'));
        const previousError = console.error;
        try {
            console.error = () => {};
            await click(document.querySelector('#MouseLayer #mos'));
        } finally { console.error = previousError; }
        const statusPanel = document.querySelector('.focus-status-panel');
        assert.match(statusPanel.textContent, /Neplatný pohyb do MOS/);
        assert.match(statusPanel.textContent, /Vybraná jednotka: A Paříž/);
        assert.match(statusPanel.textContent, /Vybraný cíl: MOS/);
        assert.ok(statusPanel.querySelector('[role="alert"]'));
        assertStableMap();
        await click(document.querySelector('#MouseLayer #bur'));
        assert.deepEqual(calls.findLast(([method, url]) => method === 'POST' && url === 'orders/games/1/'),
            ['POST', 'orders/games/1/', { unit_id: 1, order_type: 'move', target: 'BUR' }]);
        assert.match(document.querySelector('.focus-status-panel').textContent, /Rozkaz byl uložen/);
        assertStableMap();
        assert.equal(document.querySelector('.game-map svg'), originalSvg);
        await click(button('Ukončit herní režim'));
        assert.equal(document.querySelector('.focus-status-panel'), null);
        assert.match(document.querySelector('.focus-map-area').textContent, /Rozkaz byl uložen/);
        const savedArrows = document.querySelector('#ReactOrderLayer').innerHTML;
        const centerFill = document.querySelector('#_par').style.fill;
        await click(button('Označit rozkazy'));
        assert.ok(button('Znovu upravovat'));
        assert.ok(document.querySelector('fieldset').disabled);
        await click(manualOrders.querySelector('summary'));
        assert.equal(manualOrders.open, true);
        assert.ok(manualOrders.querySelector('fieldset').disabled);
        await click(button('Mapa na celou obrazovku'));
        await mapClick();
        assert.equal(document.querySelector('#ReactOrderWheel'), null);
        assert.equal(document.querySelectorAll('.game-map').length, 1);
        assert.equal(document.querySelector('.game-map'), originalMap);
        // Narrow-screen toggles keep both component owners mounted.
        await act(async () => mediaListener({ matches: true }));
        assert.ok(document.querySelector('.focus-status-overlay'));
        assertStableMap();
        await click(document.querySelector('.focus-mobile-switch button:last-child'));
        assert.equal(document.querySelector('.focus-status-overlay'), null);
        assert.equal(document.querySelector('.focus-map-area').hidden, true);
        assert.equal(document.getElementById('game-panel-diplomacy').hidden, false);
        assert.equal(document.querySelector('.game-chat'), chat);
        await click(document.querySelector('.focus-mobile-switch button:first-child'));
        assert.equal(document.querySelector('.focus-map-area').hidden, false);
        assert.equal(document.getElementById('game-panel-diplomacy').hidden, true);
        await act(async () => mediaListener({ matches: false }));
        await click(button('Ukončit herní režim'));

        assert.match(document.body.textContent, /Rozkazy jsou uzamčené/);
        assert.equal(document.querySelector('#ReactOrderWheel'), null);
        assert.equal(document.querySelector('#ReactOrderLayer').innerHTML, savedArrows);
        assert.equal(document.querySelector('#_par').style.fill, centerFill);
        await mapClick();
        assert.equal(document.querySelector('#ReactOrderWheel'), null);
        const posts = calls.filter(([method]) => method === 'POST').length;
        await act(async () => document.querySelector('fieldset').closest('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })));
        assert.equal(calls.filter(([method]) => method === 'POST').length, posts);
        await click(button('Diplomacie'));
        assert.equal(document.querySelector('.game-chat'), chat);
        await click(document.querySelector('.game-chat button[aria-pressed]'));
        assert.ok(document.querySelector('.chat-compose textarea'));
        await click(button('Hra'));
        assert.ok(button('Znovu upravovat'));
        await click(button('Znovu upravovat'));
        assert.equal(document.querySelector('fieldset').disabled, false);
        await mapClick();
        assert.ok(document.querySelector('#ReactOrderWheel'));
        failPost = true;
        await click(button('Označit rozkazy'));
        assert.match(document.querySelector('.phase-readiness').textContent, /Zkus to znovu/);
        assert.equal(button('Označit rozkazy').disabled, false);
        assert.equal(document.querySelector('fieldset').disabled, false);
        failPost = false;

        // A slow GET cannot overlap the next polling tick.
        let release;
        pendingGet = new Promise((resolve) => { release = resolve; });
        await poll();
        const gets = calls.filter(([, url]) => url.endsWith('/readiness/')).length;
        await poll();
        assert.equal(calls.filter(([, url]) => url.endsWith('/readiness/')).length, gets);
        await click(button('Označit rozkazy'));
        assert.ok(document.querySelector('fieldset').disabled);
        await act(async () => { pendingGet = null; release(); });
        assert.ok(button('Znovu upravovat'));
        await click(button('Znovu upravovat'));

        let previousGets = countGets();
        await click(button('Mapa na celou obrazovku'));
        phaseId++; manual = true;
        await poll();
        assert.ok(document.querySelector('[role="dialog"]'));
        assert.equal(document.querySelector('.game-map'), originalMap);
        assert.equal(document.querySelectorAll('.game-map').length, 1);
        assert.equal(document.querySelector('.game-chat'), chat);
        await click(button('Ukončit herní režim'));
        assert.ok(countGets() > previousGets);
        assert.ok(button('Vyhodnotit fázi nyní'));
        previousGets = countGets();
        lastReady = true;
        await click(button('Označit rozkazy'));
        assert.ok(countGets() > previousGets);
        assert.ok(button('Označit rozkazy'));
        assert.equal(document.querySelector('fieldset').disabled, false);
        lastReady = false;

        phaseId++; phaseType = 'retreat'; manual = false;
        await poll();
        assert.equal(document.querySelector('.game-manual-orders'), null);
        assert.ok(document.querySelector('.game-all-units'));
        assert.deepEqual([...document.querySelector('.game-secondary-panels').children], [document.querySelector('.game-all-units')]);
        assert.match(document.querySelector('.phase-readiness').textContent, /Ústupová fáze se ukončí automaticky/);
        assert.equal(button('Označit rozkazy'), undefined);
        await click(document.querySelector('#ReactUnitLayer > g'));
        assert.match(document.querySelector('#ReactOrderWheel').textContent, /RETREAT/);

        phaseId++; phaseType = 'adjustment'; disbands = 1;
        await poll();
        assert.equal(document.querySelector('.game-manual-orders'), null);
        assert.ok(document.querySelector('.game-all-units'));
        assert.deepEqual([...document.querySelector('.game-secondary-panels').children], [document.querySelector('.game-all-units')]);
        assert.ok(button('Označit rozkazy').disabled);
        assert.match(document.querySelector('.phase-readiness').textContent, /povinné DISBAND/);
        disbands = 0;
        await poll();
        assert.equal(button('Označit rozkazy').disabled, false);
        await click(button('Označit rozkazy'));
        assert.ok(button('Zrušit').disabled);
        await mapClick();
        assert.equal(document.querySelector('#ReactOrderWheel'), null);
        await click(button('Znovu upravovat'));
        assert.equal(button('Zrušit').disabled, false);

        phaseId++; builds = 2;
        await poll();
        assert.match(document.querySelector('.phase-readiness').textContent, /nevyužité stavby propadnou/);
        await click(button('Brest'));
        assert.ok(document.querySelector('#ReactBuildWheel'));
        await click(button('Označit rozkazy'));
        assert.equal(document.querySelector('#ReactBuildWheel'), null);
        assert.ok(button('Brest').disabled);
        assert.ok(button('Zrušit').disabled);
        await click(button('Znovu upravovat'));
        assert.equal(button('Brest').disabled, false);
        required = false;
        await poll();
        assert.equal(button('Označit rozkazy'), undefined);
        assert.match(document.querySelector('.phase-readiness').textContent, /nemáš žádné rozkazy/);
        assert.equal(document.querySelector('.game-chat'), chat);
        await click(button('Mapa na celou obrazovku'));
        await act(async () => root.unmount());
        root = null;
        assert.equal(timers.size, 0);
        assert.equal(document.body.style.overflow, '');
        assert.equal(document.documentElement.style.overflow, '');
    } finally {
        if (root) await act(async () => root.unmount());
        Object.assign(globalThis, originals);
        delete globalThis.__readinessTest;
        dom.window.close();
        assert.ok(dir.startsWith(resolve('node_modules') + sep));
        await rm(dir, { recursive: true, force: true });
    }
});
