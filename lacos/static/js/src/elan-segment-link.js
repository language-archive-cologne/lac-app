/**
 * Shareable ELAN segment links (issue #1).
 *
 * A segment link is a W3C Media Fragments anchor appended to a resource's
 * handle URL, carrying a time range and optionally the ELAN annotation id:
 *
 *   https://hdl.handle.net/11341/<pid>#t=20.5,24.0&id=a1
 *
 * The time range is authoritative. The annotation id is advisory: it pins the
 * link to an exact row while the .eaf is untouched, but ELAN renumbers
 * ANNOTATION_IDs on some exports, so a stale id is ignored rather than
 * followed. That way the id can only ever sharpen a link, never misdirect it.
 */

/**
 * Tolerance, in seconds, when comparing a hash offset against a row offset.
 *
 * The template emits offsets rounded to milliseconds, so our own links differ
 * from the parsed annotation by at most 0.0005s. The wider window also absorbs
 * offsets a human rounded by hand.
 */
const OFFSET_TOLERANCE = 0.01;

/** Parse one Media Fragments time value ("npt:20.5,24.0", "20.5", ",24.0"). */
function parseTimeDimension(value) {
  // Named time schemes are optional and default to npt; we only speak npt.
  const withoutScheme = value.startsWith('npt:') ? value.slice(4) : value;
  if (!withoutScheme) return undefined;

  const [startText, endText, ...rest] = withoutScheme.split(',');
  if (rest.length) return undefined;

  const bound = (text) => {
    if (text === undefined || text === '') return null;
    const parsed = Number(text);
    return Number.isFinite(parsed) ? parsed : undefined;
  };

  const start = bound(startText);
  const end = bound(endText);
  if (start === undefined || end === undefined) return undefined;
  if (start === null && end === null) return undefined;
  if (start !== null && start < 0) return undefined;
  if (end !== null && end < 0) return undefined;
  if (start !== null && end !== null && end <= start) return undefined;

  return { start, end };
}

/**
 * Parse a location hash into a segment request.
 *
 * @param {string|null|undefined} hash Hash with or without its leading "#".
 * @returns {{start: number|null, end: number|null, id: string|null}|null}
 *   null when the hash carries no usable segment dimension, or when the time
 *   range it carries is malformed.
 */
export function parseSegmentHash(hash) {
  if (typeof hash !== 'string') return null;

  const body = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!body) return null;

  let time = null;
  let id = null;

  for (const part of body.split('&')) {
    const separator = part.indexOf('=');
    if (separator < 0) continue;

    const name = part.slice(0, separator);
    const value = decodeURIComponent(part.slice(separator + 1));

    if (name === 't') {
      const parsed = parseTimeDimension(value);
      // A malformed time range invalidates the whole anchor: better to land on
      // the page unpositioned than to seek somewhere we were not asked to.
      if (parsed === undefined) return null;
      time = parsed;
    } else if (name === 'id' && value) {
      id = value;
    }
  }

  if (!time && !id) return null;

  return {
    start: time ? time.start : null,
    end: time ? time.end : null,
    id,
  };
}

/** True when a row is time-aligned and so can be matched against an offset. */
function isAligned(row) {
  return typeof row.start === 'number' && Number.isFinite(row.start);
}

/** Find the row a bare offset points at, or null. */
function rowForOffset(rows, offset) {
  // Our own links carry a row's exact start, so try that first — it stays
  // unambiguous even where annotation intervals overlap across tiers.
  const exact = rows.find(
    (row) => isAligned(row) && Math.abs(row.start - offset) <= OFFSET_TOLERANCE,
  );
  if (exact) return exact;

  // Otherwise treat the offset as a moment and take the segment spanning it,
  // innermost first, which is what a hand-written "#t=22" means.
  let containing = null;
  for (const row of rows) {
    if (!isAligned(row)) continue;
    const end = typeof row.end === 'number' ? row.end : Infinity;
    if (row.start <= offset && offset < end) {
      if (!containing || row.start > containing.start) containing = row;
    }
  }
  return containing;
}

/**
 * Resolve a parsed segment request against the rows of an annotation table.
 *
 * @param {Array<{id: string, start: number|null, end: number|null}>} rows
 * @param {{start: number|null, end: number|null, id: string|null}|null} parsed
 * @returns {{row: object|null, start: number|null, end: number|null,
 *            matched: boolean}|null}
 *   `matched` is false when playback should seek without highlighting a row.
 *   null when there is nothing to resolve.
 */
export function resolveSegment(rows, parsed) {
  if (!parsed) return null;

  const { start, end, id } = parsed;
  const hasTime = start !== null || end !== null;
  if (!hasTime && !id) return null;

  const fromRow = (row) => ({
    row,
    start: row.start,
    end: row.end,
    matched: true,
  });

  if (id) {
    const row = rows.find((candidate) => candidate.id === id);
    if (row) {
      // Without a time range the id is all we have, so trust it.
      if (!hasTime) return fromRow(row);
      // With one, the id only stands if it agrees — otherwise it is stale.
      if (
        start !== null &&
        isAligned(row) &&
        Math.abs(row.start - start) <= OFFSET_TOLERANCE
      ) {
        return fromRow(row);
      }
    }
  }

  if (start !== null) {
    const row = rowForOffset(rows, start);
    if (row) return fromRow(row);
  }

  return { row: null, start, end, matched: false };
}

/** Read one numeric data attribute, or null when absent or unparseable. */
function offsetAttribute(element, name) {
  const raw = element.getAttribute(name);
  if (raw === null || raw === '') return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

/**
 * Collect the annotation rows rendered into an ELAN viewer.
 *
 * @param {ParentNode} root Element containing the annotation table.
 * @returns {Array<{id: string, start: number|null, end: number|null,
 *                  element: Element}>}
 */
export function readAnnotationRows(root) {
  if (!root) return [];

  return Array.from(root.querySelectorAll('tr[data-annotation-id]')).map(
    (element) => ({
      id: element.getAttribute('data-annotation-id'),
      start: offsetAttribute(element, 'data-annotation-start'),
      end: offsetAttribute(element, 'data-annotation-end'),
      element,
    }),
  );
}

/**
 * Position an ELAN viewer on the segment named by a location hash.
 *
 * Seeks and highlights but deliberately does not play: autoplay without a user
 * gesture is blocked by browsers, and a cited link should open ready to play
 * rather than start talking. Pangloss positions the same way.
 *
 * @param {ParentNode} root Element containing the annotation table.
 * @param {object} options
 * @param {string} options.hash Location hash to honour.
 * @param {function(number, number|null): void} [options.seek] Called with the
 *   segment bounds when there is somewhere to seek to.
 * @param {string} [options.highlightClass] Class marking the cited row.
 * @returns {object|null} The resolution, or null when there was nothing to do.
 */
export function initSegmentLink(root, options = {}) {
  const { hash, seek, highlightClass = 'bg-blue-100' } = options;

  const parsed = parseSegmentHash(hash);
  if (!parsed) return null;

  const result = resolveSegment(readAnnotationRows(root), parsed);
  if (!result) return null;
  // An id-only link naming a row this file no longer has: nothing to seek to
  // and nothing to mark, so leave the page as it loaded.
  if (!result.matched && result.start === null) return null;

  if (result.start !== null && typeof seek === 'function') {
    seek(result.start, result.end);
  }

  if (result.matched && result.row && result.row.element) {
    const { element } = result.row;
    element.classList.add(highlightClass);
    if (typeof element.scrollIntoView === 'function') {
      element.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }

  return result;
}
