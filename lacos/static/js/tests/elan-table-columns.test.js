/**
 * Tests for the ELAN annotation-table column reorder/resize module.
 *
 * Covers the pure layout helpers (reorder math, storage-key derivation,
 * saved-layout compatibility) plus a jsdom round-trip of apply/serialize and
 * localStorage persistence (issue #142 follow-up — ELAN player improvements).
 */

/* eslint-env jest */

import {
  moveColumn,
  layoutStorageKey,
  isLayoutCompatible,
  serializeLayout,
  applyLayout,
  ensureFixed,
  initElanTableColumns,
} from '../src/elan-table-columns.js';

// ─── moveColumn ──────────────────────────────────────────────────────────

describe('moveColumn', () => {
  const base = ['a', 'b', 'c', 'd'];

  test('inserts the moved key before the target key', () => {
    expect(moveColumn(base, 'a', 'c')).toEqual(['b', 'a', 'c', 'd']);
    expect(moveColumn(base, 'd', 'b')).toEqual(['a', 'd', 'b', 'c']);
  });

  test('appends when the target key is null', () => {
    expect(moveColumn(base, 'b', null)).toEqual(['a', 'c', 'd', 'b']);
  });

  test('is a no-op when moving a key onto itself', () => {
    expect(moveColumn(base, 'b', 'b')).toEqual(base);
  });

  test('returns an unchanged copy when the key is absent', () => {
    const result = moveColumn(base, 'z', 'a');
    expect(result).toEqual(base);
    expect(result).not.toBe(base);
  });

  test('does not mutate the input array', () => {
    const input = ['a', 'b', 'c'];
    moveColumn(input, 'c', 'a');
    expect(input).toEqual(['a', 'b', 'c']);
  });
});

// ─── layoutStorageKey ────────────────────────────────────────────────────

describe('layoutStorageKey', () => {
  test('is independent of tier-key ordering (set identity)', () => {
    expect(layoutStorageKey('R1', ['tx', 'tl'])).toBe(
      layoutStorageKey('R1', ['tl', 'tx'])
    );
  });

  test('differs by resource id', () => {
    expect(layoutStorageKey('R1', ['tx'])).not.toBe(
      layoutStorageKey('R2', ['tx'])
    );
  });

  test('differs by tier set', () => {
    expect(layoutStorageKey('R1', ['tx'])).not.toBe(
      layoutStorageKey('R1', ['tx', 'tl'])
    );
  });
});

// ─── isLayoutCompatible ──────────────────────────────────────────────────

describe('isLayoutCompatible', () => {
  test('true when saved order is the same set of tiers', () => {
    expect(isLayoutCompatible({ order: ['tl', 'tx'] }, ['tx', 'tl'])).toBe(true);
  });

  test('false when a tier is missing or added', () => {
    expect(isLayoutCompatible({ order: ['tx'] }, ['tx', 'tl'])).toBe(false);
    expect(isLayoutCompatible({ order: ['tx', 'tl', 'gl'] }, ['tx', 'tl'])).toBe(false);
  });

  test('false for empty/garbage state', () => {
    expect(isLayoutCompatible(null, ['tx'])).toBe(false);
    expect(isLayoutCompatible({}, ['tx'])).toBe(false);
    expect(isLayoutCompatible({ order: [] }, ['tx'])).toBe(false);
  });
});

// ─── DOM round-trip + persistence ────────────────────────────────────────

function buildTable() {
  document.body.innerHTML = `
    <table data-elan-table data-resource-id="R1">
      <thead><tr>
        <th data-col-key="__play"></th>
        <th data-col-key="__time" data-col-resizable>Time</th>
        <th data-col-key="tx" data-col-reorder data-col-resizable>tx</th>
        <th data-col-key="tl" data-col-reorder data-col-resizable>tl</th>
      </tr></thead>
      <tbody>
        <tr>
          <td data-col-key="__play">play</td>
          <td data-col-key="__time">0.0s</td>
          <td data-col-key="tx">hello</td>
          <td data-col-key="tl">hallo</td>
        </tr>
      </tbody>
    </table>`;
  return document.querySelector('[data-elan-table]');
}

function rowKeys(table) {
  return [...table.querySelectorAll('tbody tr:first-child td')].map(
    (td) => td.dataset.colKey
  );
}
function headerKeys(table) {
  return [...table.querySelectorAll('thead th')].map((th) => th.dataset.colKey);
}

describe('applyLayout / serializeLayout', () => {
  test('applyLayout reorders header and body cells together', () => {
    const table = buildTable();
    applyLayout(table, { order: ['tl', 'tx'], widths: {} });
    expect(headerKeys(table)).toEqual(['__play', '__time', 'tl', 'tx']);
    expect(rowKeys(table)).toEqual(['__play', '__time', 'tl', 'tx']);
  });

  test('applyLayout sets pixel widths on resizable columns', () => {
    const table = buildTable();
    applyLayout(table, { order: ['tx', 'tl'], widths: { tx: 240 } });
    const th = table.querySelector('th[data-col-key="tx"]');
    expect(th.style.width).toBe('240px');
  });

  test('serialize then apply is a stable round-trip', () => {
    const table = buildTable();
    applyLayout(table, { order: ['tl', 'tx'], widths: { tl: 180 } });
    const state = serializeLayout(table);
    expect(state.order).toEqual(['tl', 'tx']);
    expect(state.widths.tl).toBe(180);
  });
});

describe('ensureFixed', () => {
  test('switches the table to fixed layout with explicit widths', () => {
    const table = buildTable();
    ensureFixed(table);
    expect(table.style.tableLayout).toBe('fixed');
    expect(table.dataset.fixed).toBe('1');
    expect(parseInt(table.style.width, 10)).toBeGreaterThan(0);
    // Body cells clip instead of forcing the column wider.
    expect(table.querySelector('tbody td').style.overflow).toBe('hidden');
  });

  test('preserves widths already set on the headers', () => {
    const table = buildTable();
    applyLayout(table, { order: ['tx', 'tl'], widths: { tx: 240 } });
    ensureFixed(table);
    expect(table.querySelector('th[data-col-key="tx"]').style.width).toBe('240px');
  });
});

describe('resize wiring', () => {
  beforeEach(() => window.localStorage.clear());

  test('adds a visible resize handle to each resizable header', () => {
    const table = buildTable();
    initElanTableColumns(table);
    // __time, tx, tl — the play column is not resizable.
    expect(table.querySelectorAll('.elan-col-resize-handle').length).toBe(3);
  });
});

describe('initElanTableColumns persistence', () => {
  beforeEach(() => window.localStorage.clear());

  test('restores a compatible saved layout on init', () => {
    const table = buildTable();
    const key = layoutStorageKey('R1', ['tx', 'tl']);
    window.localStorage.setItem(
      key,
      JSON.stringify({ order: ['tl', 'tx'], widths: { tl: 200 } })
    );

    initElanTableColumns(table);

    expect(headerKeys(table)).toEqual(['__play', '__time', 'tl', 'tx']);
    expect(table.querySelector('th[data-col-key="tl"]').style.width).toBe('200px');
  });

  test('ignores an incompatible saved layout', () => {
    const table = buildTable();
    const key = layoutStorageKey('R1', ['tx', 'tl']);
    window.localStorage.setItem(
      key,
      JSON.stringify({ order: ['tl', 'tx', 'gone'], widths: {} })
    );

    initElanTableColumns(table);

    // Falls back to the file's default order.
    expect(headerKeys(table)).toEqual(['__play', '__time', 'tx', 'tl']);
  });
});
