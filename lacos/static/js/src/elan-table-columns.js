/**
 * ELAN annotation-table column controls.
 *
 * Adds two interactions to the ELAN annotation table:
 *   - reorder tier columns by dragging a tier header left/right
 *   - resize a column by dragging its right edge
 *
 * The arrangement (tier order + column widths) is remembered per ELAN file in
 * localStorage, keyed by the resource id and its tier set. A saved layout is
 * only restored when its tier set still matches the file (guards tier drift).
 *
 * Plain ES module — self-initialises on DOMContentLoaded (standalone page) and
 * on htmx:afterSwap (modal), mirroring facet-filter.js. No framework.
 */

const STORAGE_PREFIX = 'elan-cols:v1:';
const MIN_COL_PX = 60;

// ─── Pure helpers ─────────────────────────────────────────────────────────

/** Move `fromKey` to immediately before `beforeKey` (append when null). Pure. */
export function moveColumn(order, fromKey, beforeKey) {
  if (!order.includes(fromKey) || fromKey === beforeKey) {
    return order.slice();
  }
  const next = order.filter((key) => key !== fromKey);
  const idx = beforeKey == null ? -1 : next.indexOf(beforeKey);
  if (idx === -1) {
    next.push(fromKey);
  } else {
    next.splice(idx, 0, fromKey);
  }
  return next;
}

/** Stable localStorage key for a resource's tier set (order-independent). */
export function layoutStorageKey(resourceId, tierKeys) {
  const tiers = [...tierKeys].sort().join('|');
  return `${STORAGE_PREFIX}${resourceId}:${tiers}`;
}

/** A saved layout is usable only if its tiers are exactly the current tiers. */
export function isLayoutCompatible(state, tierKeys) {
  if (!state || !Array.isArray(state.order) || state.order.length === 0) {
    return false;
  }
  const saved = new Set(state.order);
  return saved.size === tierKeys.length && tierKeys.every((key) => saved.has(key));
}

// ─── DOM helpers ──────────────────────────────────────────────────────────

function reorderableKeys(table) {
  return [...table.querySelectorAll('thead th[data-col-reorder]')].map(
    (th) => th.dataset.colKey
  );
}

function headerCell(table, key) {
  return (
    [...table.querySelectorAll('thead th')].find(
      (th) => th.dataset.colKey === key
    ) || null
  );
}

function allRows(table) {
  const head = table.querySelector('thead tr');
  return [head, ...table.querySelectorAll('tbody tr')].filter(Boolean);
}

const DEFAULT_WIDTHS = { __play: 56, __time: 150 };
const DEFAULT_TIER_WIDTH = 200;

function defaultWidthFor(th) {
  return DEFAULT_WIDTHS[th.dataset.colKey] || DEFAULT_TIER_WIDTH;
}

function applyWidth(th, px) {
  const width = `${px}px`;
  th.style.width = width;
  th.style.minWidth = width;
  th.style.maxWidth = width;
  th.style.overflow = 'hidden';
}

function recalcTableWidth(table) {
  const sum = [...table.querySelectorAll('thead th')].reduce(
    (total, th) => total + (parseInt(th.style.width, 10) || 0),
    0
  );
  if (sum > 0) {
    table.style.width = `${sum}px`;
  }
}

/**
 * Switch the table to fixed layout so column widths become authoritative.
 *
 * Under the default `table-layout: auto` with `whitespace-nowrap` cells, the
 * widest body cell dictates column width and an explicit `<th>` width is
 * ignored — so resizing has no visible effect. Fixed layout makes the `<th>`
 * width win; body cells clip with an ellipsis. Idempotent.
 */
export function ensureFixed(table) {
  const ths = [...table.querySelectorAll('thead th')];
  if (!ths.length) {
    return;
  }
  if (table.dataset.fixed !== '1') {
    ths.forEach((th) => {
      let width = parseInt(th.style.width, 10);
      if (Number.isNaN(width)) {
        const measured = Math.round(th.getBoundingClientRect().width);
        width = measured > 0 ? measured : defaultWidthFor(th);
      }
      applyWidth(th, width);
    });
    table.querySelectorAll('tbody td').forEach((td) => {
      td.style.overflow = 'hidden';
      td.style.textOverflow = 'ellipsis';
    });
    table.style.tableLayout = 'fixed';
    table.dataset.fixed = '1';
  }
  recalcTableWidth(table);
}

function setColumnWidth(table, key, px) {
  const th = headerCell(table, key);
  if (th) {
    applyWidth(th, px);
    recalcTableWidth(table);
  }
}

/** Revert to the default auto layout / content-fitted widths. */
function clearWidths(table) {
  table.querySelectorAll('thead th').forEach((th) => {
    th.style.width = '';
    th.style.minWidth = '';
    th.style.maxWidth = '';
    th.style.overflow = '';
  });
  table.querySelectorAll('tbody td').forEach((td) => {
    td.style.overflow = '';
    td.style.textOverflow = '';
  });
  table.style.tableLayout = '';
  table.style.width = '';
  delete table.dataset.fixed;
}

/** Reorder one row's tier cells to `tierOrder`, leaving fixed cells in place. */
function reorderRow(row, tierOrder, tierKeySet) {
  const cellByKey = new Map();
  [...row.children].forEach((cell) => {
    if (tierKeySet.has(cell.dataset.colKey)) {
      cellByKey.set(cell.dataset.colKey, cell);
    }
  });
  // Fixed columns are always leftmost, so re-appending tier cells in order
  // yields [fixed…, tiers in tierOrder].
  tierOrder.forEach((key) => {
    const cell = cellByKey.get(key);
    if (cell) row.appendChild(cell);
  });
}

/** Read the current arrangement (tier order + widths) from the DOM. */
export function serializeLayout(table) {
  const widths = {};
  table.querySelectorAll('thead th[data-col-resizable]').forEach((th) => {
    const value = parseInt(th.style.width, 10);
    if (!Number.isNaN(value)) {
      widths[th.dataset.colKey] = value;
    }
  });
  return { order: reorderableKeys(table), widths };
}

/** Apply a saved arrangement to the DOM. */
export function applyLayout(table, state) {
  if (!state) {
    return;
  }
  const tierKeySet = new Set(reorderableKeys(table));
  if (Array.isArray(state.order) && state.order.length) {
    const tierOrder = state.order.filter((key) => tierKeySet.has(key));
    allRows(table).forEach((row) => reorderRow(row, tierOrder, tierKeySet));
  }
  if (state.widths) {
    Object.entries(state.widths).forEach(([key, px]) => {
      if (tierKeySet.has(key) || headerCell(table, key)?.hasAttribute('data-col-resizable')) {
        setColumnWidth(table, key, px);
      }
    });
  }
}

// ─── Wiring ───────────────────────────────────────────────────────────────

function safeLocalStorage() {
  try {
    return window.localStorage;
  } catch (err) {
    return null;
  }
}

function wireResize(table, persist) {
  const hint = table.dataset.resizeHint || 'Drag to resize column';

  table.querySelectorAll('thead th[data-col-resizable]').forEach((th) => {
    if (th.querySelector('.elan-col-resize-handle')) {
      return;
    }
    th.style.position = 'relative';

    const handle = document.createElement('span');
    handle.className = 'elan-col-resize-handle';
    handle.title = hint;
    handle.setAttribute('aria-hidden', 'true');

    handle.addEventListener('dragstart', (event) => event.preventDefault());

    handle.addEventListener('mousedown', (event) => {
      event.preventDefault();
      event.stopPropagation(); // never start a reorder drag from the handle
      ensureFixed(table);
      const startX = event.clientX;
      const startWidth =
        parseInt(th.style.width, 10) || Math.round(th.getBoundingClientRect().width);

      const onMove = (moveEvent) => {
        const width = Math.max(
          MIN_COL_PX,
          Math.round(startWidth + (moveEvent.clientX - startX))
        );
        setColumnWidth(table, th.dataset.colKey, width);
      };
      const onUp = () => {
        document.removeEventListener('mousemove', onMove);
        document.removeEventListener('mouseup', onUp);
        document.body.style.cursor = '';
        persist();
      };
      document.body.style.cursor = 'col-resize';
      document.addEventListener('mousemove', onMove);
      document.addEventListener('mouseup', onUp);
    });

    th.appendChild(handle);
  });
}

function clearDropMarkers(ths) {
  ths.forEach((th) => th.classList.remove('ring-2', 'ring-primary'));
}

function wireReorder(table, persist) {
  const ths = [...table.querySelectorAll('thead th[data-col-reorder]')];
  let dragKey = null;

  ths.forEach((th) => {
    th.setAttribute('draggable', 'true');
    if (!th.style.cursor) {
      th.style.cursor = 'grab';
    }

    th.addEventListener('dragstart', (event) => {
      dragKey = th.dataset.colKey;
      event.dataTransfer.effectAllowed = 'move';
      try {
        event.dataTransfer.setData('text/plain', dragKey);
      } catch (err) {
        /* some browsers restrict setData — drag still works via dragKey */
      }
      th.classList.add('opacity-50');
    });

    th.addEventListener('dragend', () => {
      dragKey = null;
      th.classList.remove('opacity-50');
      clearDropMarkers(ths);
    });

    th.addEventListener('dragover', (event) => {
      if (dragKey == null || th.dataset.colKey === dragKey) {
        return;
      }
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      clearDropMarkers(ths);
      th.classList.add('ring-2', 'ring-primary');
    });

    th.addEventListener('drop', (event) => {
      event.preventDefault();
      const from =
        dragKey || (event.dataTransfer && event.dataTransfer.getData('text/plain'));
      const to = th.dataset.colKey;
      clearDropMarkers(ths);
      if (!from || from === to) {
        return;
      }
      applyLayout(table, { order: moveColumn(reorderableKeys(table), from, to) });
      persist();
    });
  });
}

function wireReset(table, defaultOrder, persist, storage, resourceId, tierKeys) {
  const root = table.closest('[data-viewer-type]') || document;
  const button = root.querySelector('[data-elan-reset]');
  if (!button) {
    return;
  }
  button.addEventListener('click', () => {
    clearWidths(table);
    applyLayout(table, { order: defaultOrder });
    if (storage && resourceId && tierKeys.length) {
      try {
        storage.removeItem(layoutStorageKey(resourceId, tierKeys));
      } catch (err) {
        /* ignore */
      }
    }
  });
}

/** Initialise reorder/resize/persistence on one ELAN table. Idempotent. */
export function initElanTableColumns(table, opts = {}) {
  if (!table || table.dataset.colsInit === '1') {
    return;
  }
  table.dataset.colsInit = '1';

  const storage = opts.storage || safeLocalStorage();
  const resourceId = table.dataset.resourceId || '';
  const tierKeys = reorderableKeys(table);
  const defaultOrder = tierKeys.slice();

  if (storage && resourceId && tierKeys.length) {
    const raw = storage.getItem(layoutStorageKey(resourceId, tierKeys));
    if (raw) {
      let state = null;
      try {
        state = JSON.parse(raw);
      } catch (err) {
        state = null;
      }
      if (isLayoutCompatible(state, tierKeys)) {
        applyLayout(table, state);
      }
    }
  }

  const persist = () => {
    if (!storage || !resourceId || !tierKeys.length) {
      return;
    }
    try {
      storage.setItem(
        layoutStorageKey(resourceId, tierKeys),
        JSON.stringify(serializeLayout(table))
      );
    } catch (err) {
      /* quota / disabled — ignore */
    }
  };

  wireResize(table, persist);
  wireReorder(table, persist);
  wireReset(table, defaultOrder, persist, storage, resourceId, tierKeys);

  // Switch to fixed layout once the table has been laid out, so column widths
  // become authoritative. Deferred a frame so measurements are valid even when
  // the table is initially inside a not-yet-shown modal.
  const raf =
    typeof window !== 'undefined' && window.requestAnimationFrame
      ? window.requestAnimationFrame.bind(window)
      : (callback) => callback();
  raf(() => ensureFixed(table));
}

// ─── Self-initialisation (browser only) ────────────────────────────────────

function initAll(root) {
  (root || document)
    .querySelectorAll('table[data-elan-table]')
    .forEach((table) => initElanTableColumns(table));
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => initAll(document));
  document.addEventListener('htmx:afterSwap', (event) => {
    const target = (event.detail && event.detail.target) || document;
    if (target.matches && target.matches('table[data-elan-table]')) {
      initElanTableColumns(target);
    }
    if (target.querySelectorAll) {
      initAll(target);
    }
  });
}
