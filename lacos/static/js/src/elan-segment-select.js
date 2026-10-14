/**
 * Multi-segment range citation for ELAN tables.
 *
 * A citation is a time range. This module lets the user tick any set of
 * annotation rows and copy a single shareable link spanning them:
 *
 *   https://hdl.handle.net/11341/<pid>#t=56.220,58.510
 *
 * The emitted anchor is consumed by elan-segment-link.js, which highlights
 * every row the range overlaps, so the cited span shows in full. The per-row
 * single-segment link icon is left untouched — a range of one row is its
 * degenerate case.
 *
 * Plain ES module — self-initialises on DOMContentLoaded (standalone page) and
 * on htmx:afterSwap (modal), mirroring elan-table-columns.js.
 */

function formatOffset(value) {
  return value.toFixed(3);
}

/**
 * Build the range anchor for a set of aligned [start, end] pairs.
 *
 * @param {Array<[number, number]>} spans
 * @returns {string|null} e.g. "#t=56.220,58.510", or null when there is
 *   nothing citeable (no spans, or no usable bounds).
 */
export function buildRangeAnchor(spans) {
  const aligned = spans.filter(
    ([start, end]) =>
      Number.isFinite(start) && Number.isFinite(end) && end > start,
  );
  if (!aligned.length) return null;

  const start = Math.min(...aligned.map(([s]) => s));
  const end = Math.max(...aligned.map(([, e]) => e));
  return `#t=${formatOffset(start)},${formatOffset(end)}`;
}

/** Read the checked row offsets out of one ELAN scope. */
function selectedSpans(scope) {
  return Array.from(
    scope.querySelectorAll('input.elan-segment-check:checked'),
  ).map((input) => {
    const start = parseFloat(input.dataset.annotationStart);
    const end = parseFloat(input.dataset.annotationEnd);
    return [start, end];
  });
}

function syncPlayer(scope, play = false, fallback = null) {
  const anchor = buildRangeAnchor(selectedSpans(scope));
  const [start, end] = anchor ? anchor.slice(3).split(',').map(Number) : (fallback || [null, null]);
  scope.dispatchEvent(new CustomEvent('elan:selection', {
    bubbles: true,
    detail: { start, end, play },
  }));
}

function updateBar(scope, bar) {
  syncPlayer(scope);
  if (!bar) return;
  const count = scope.querySelectorAll('input.elan-segment-check:checked').length;
  bar.classList.toggle('hidden', count < 2);
  if (count < 2) return;

  const spans = selectedSpans(scope);
  const anchor = buildRangeAnchor(spans);
  const label = bar.querySelector('[data-range-count]');
  const copyButton = bar.querySelector('[data-copy-text]');

  if (label) {
    label.textContent = count === 2 ? '2 segments' : `${count} segments`;
  }

  if (copyButton && anchor) {
    const base = scope.dataset.segmentLinkBase || '';
    const url = `${base}${anchor}`;
    copyButton.dataset.copyText = url;
    copyButton.title = url;
    copyButton.classList.remove('opacity-50', 'pointer-events-none');
  } else {
    // No absolute handle available (e.g. the collection modal): offer the
    // bare anchor, which still works appended to any resource handle URL.
    if (copyButton) {
      copyButton.dataset.copyText = anchor;
      copyButton.title = anchor;
      copyButton.classList.remove('opacity-50', 'pointer-events-none');
    }
  }
}

function clearSelection(scope) {
  scope.querySelectorAll('input.elan-segment-check').forEach((input) => {
    input.checked = false;
  });
}

/** Wire selection + copy-range-link on one ELAN scope. Idempotent. */
export function initElanSegmentSelect(scope) {
  if (!scope || scope.dataset.segSelectInit === '1') return;
  scope.dataset.segSelectInit = '1';

  const bar = scope.querySelector('[data-elan-range-bar]');
  scope.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-annotation-start]');
    if (!button) return;
    syncPlayer(scope, true, [
      Number(button.dataset.annotationStart),
      Number(button.dataset.annotationEnd),
    ]);
  });

  scope.addEventListener('change', (event) => {
    if (event.target instanceof HTMLInputElement && event.target.classList.contains('elan-segment-check')) {
      updateBar(scope, bar);
    }
  });

  bar?.querySelector('[data-elan-range-clear]')?.addEventListener('click', () => {
    clearSelection(scope);
    updateBar(scope, bar);
  });
}

// ─── Self-initialisation (browser only) ────────────────────────────────────

function initAll(root) {
  (root || document).querySelectorAll('[data-elan-scope]').forEach(initElanSegmentSelect);
}

if (typeof document !== 'undefined') {
  document.addEventListener('DOMContentLoaded', () => initAll(document));
  document.addEventListener('htmx:afterSwap', (event) => {
    const target = (event.detail && event.detail.target) || document;
    if (target.matches && target.matches('[data-elan-scope]')) {
      initElanSegmentSelect(target);
    }
    if (target.querySelectorAll) initAll(target);
  });
}
