import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises';
import { resolve, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'vite';
import React, { act } from 'react';

test('Gulf of Lyon SVG aliases use canonical LYO throughout the real map', async (t) => {
    const dir = await mkdtemp(resolve('node_modules', '.map-alias-test-'));
    const dom = new JSDOM('<div id="root"></div>', { url: 'http://localhost' });
    const previousFetch = globalThis.fetch;
    Object.assign(globalThis, { window: dom.window, document: dom.window.document,
        DOMParser: dom.window.DOMParser, XMLSerializer: dom.window.XMLSerializer,
        IS_REACT_ACT_ENVIRONMENT: true });
    const { createRoot } = await import('react-dom/client');
    const svg = await readFile(resolve('public/maps/standard.svg'), 'utf8');
    let fixture = svg;
    globalThis.fetch = async () => ({ ok: true, text: async () => fixture });
    const root = createRoot(document.getElementById('root'));
    try {
        const bundle = await build({ logLevel: 'silent', build: { write: false, minify: false,
            lib: { entry: resolve('src/components/game/GameMap.jsx'), formats: ['es'] },
            rolldownOptions: { external: (id) => /^(react|react-dom)(\/|$)/.test(id) } } });
        const file = resolve(dir, 'map.mjs');
        await writeFile(file, (Array.isArray(bundle) ? bundle[0] : bundle).output.find((item) => item.type === 'chunk' && item.isEntry).code);
        const { default: GameMap } = await import(pathToFileURL(file).href);
        const fleet = { id: 1, unit_type: 'fleet', country: 'FRA', province_code: 'MAR' };
        const render = async (props = {}, key = 'gol') => {
            await act(async () => root.render(React.createElement(GameMap, { key, units: [fleet], ...props })));
        };
        for (const alias of ['gol', 'lyo']) {
            await t.test(`${alias} clicks emit LYO and highlight the matching province`, async () => {
                fixture = alias === 'gol' ? svg : svg.replace('id="gol"', 'id="lyo"').replace('id="_gol"', 'id="_lyo"');
                let target;
                await render({ selectedUnit: fleet, draftOrderType: 'move',
                    onProvinceClick: (code) => { target = code; } }, alias);
                const province = document.querySelector(`#MouseLayer #${alias}`);
                assert.ok(province);
                await act(async () => province.dispatchEvent(new window.MouseEvent('click', { bubbles: true })));
                assert.equal(target, 'LYO');
                await render({ selectedTarget: target }, alias);
                assert.equal(document.querySelector(`#_${alias}`).style.stroke, '#ef4444');
            });
        }
        fixture = svg;
        const cases = [
            ['saved MOVE', { order_type: 'move', target_code: 'LYO' }, {}, 'move'],
            ['historical MOVE', { order_type: 'move', target_code: 'LYO', result: 'success' }, { showHistoricalOrders: true }, 'move'],
            ['SUPPORT', { order_type: 'support', support_target_code: 'LYO' }, {}, 'support'],
            ['CONVOY', { order_type: 'convoy', convoy_target_code: 'LYO' }, {}, 'convoy'],
            ['Retreat', { order_type: 'retreat', target_code: 'LYO', saved_unit_id: 1 },
                { phaseType: 'retreat', units: [{ ...fleet, is_dislodged: true }] }, 'move'],
        ];
        for (const [name, fields, props, marker] of cases) {
            await t.test(`${name} arrow locates canonical LYO`, async () => {
                const order = { origin: 'MAR', ...fields };
                await render({ orders: [order], historicalOrders: [order], ...props });
                const arrow = document.querySelector(`#ReactOrderLayer line[marker-end="url(#${marker}-arrow)"]`);
                assert.ok(arrow, 'order must render an arrow');
                // The arrow stops just short of the canonical LYO UNIT coordinate.
                const distance = Math.hypot(Number(arrow.getAttribute('x2')) - 514.3, Number(arrow.getAttribute('y2')) - 1055);
                assert.ok(distance > 0 && distance <= 31, `arrow endpoint is ${distance} from LYO`);
            });
        }
        await t.test('a fleet in LYO renders and can move back toward MAR', async () => {
            await render({ units: [{ ...fleet, province_code: 'LYO' }],
                orders: [{ origin: 'LYO', order_type: 'move', target_code: 'MAR' }] });
            assert.ok(document.querySelector('#ReactUnitLayer').childElementCount > 0);
            assert.ok(document.querySelector('#ReactOrderLayer line[marker-end]'));
        });
    } finally {
        await act(async () => root.unmount());
        globalThis.fetch = previousFetch;
        dom.window.close();
        assert.ok(dir.startsWith(resolve('node_modules') + sep + '.map-alias-test-'));
        await rm(dir, { recursive: true, force: true });
    }
});
