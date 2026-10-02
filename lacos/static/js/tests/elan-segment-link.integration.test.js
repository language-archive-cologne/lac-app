/**
 * Runs the segment-link module against HTML captured from the running app,
 * rather than hand-written markup. Guards against the template and the module
 * drifting apart - the thing unit tests with fabricated rows cannot catch.
 *
 * Fixture: GET /bundles/11341/demo-segment-bnd/resources/11341/demo-segment-eaf/
 */

/* eslint-env jest */

import fs from 'fs';
import path from 'path';

import { initSegmentLink, readAnnotationRows } from '../src/elan-segment-link.js';

const html = fs.readFileSync(
  path.join(__dirname, '__fixture_resource_page.html'),
  'utf8',
);

function loadPage() {
  document.documentElement.innerHTML = html;
  Element.prototype.scrollIntoView = jest.fn();
  return document.querySelector('[data-viewer-type="elan"]') || document.body;
}

test('the rendered page exposes every annotation row to the module', () => {
  const rows = readAnnotationRows(loadPage());

  expect(rows.map((r) => r.id)).toEqual(['a1', 'a2', 'a3', 'a4', 'a5']);
  expect(rows[3]).toMatchObject({ id: 'a4', start: 20.5, end: 24.0 });
});

test('a cited segment link resolves against the real markup', () => {
  const root = loadPage();
  const seek = jest.fn();

  const result = initSegmentLink(root, {
    hash: '#t=20.500,24.000&id=a4',
    seek,
  });

  expect(seek).toHaveBeenCalledWith(20.5, 24.0);
  expect(result.row.id).toBe('a4');
  expect(document.getElementById('ann-a4').classList.contains('bg-blue-100')).toBe(true);
});

test('the copy buttons on the page carry anchors the module can parse back', () => {
  const root = loadPage();
  // The page also carries resource-level handle copy buttons with no
  // fragment; only the per-segment ones are this module's concern.
  const buttons = Array.from(root.querySelectorAll('[data-copy-text]')).filter(
    (button) => button.getAttribute('data-copy-text').includes('#t='),
  );

  expect(buttons.length).toBe(5);

  // Round-trip: every link the UI hands out must resolve to its own row.
  buttons.forEach((button) => {
    const hash = button.getAttribute('data-copy-text').replace(/^[^#]*/, '');
    const fresh = loadPage();
    const result = initSegmentLink(fresh, { hash, seek: jest.fn() });
    expect(result).not.toBeNull();
    expect(result.matched).toBe(true);
  });
});

test('a hand-written offset inside an utterance lands on that utterance', () => {
  const result = initSegmentLink(loadPage(), { hash: '#t=22', seek: jest.fn() });

  expect(result.row.id).toBe('a4');
});

test('a stale annotation id still resolves via its time range', () => {
  const result = initSegmentLink(loadPage(), {
    hash: '#t=24.000,29.750&id=a2',
    seek: jest.fn(),
  });

  expect(result.row.id).toBe('a5');
});
