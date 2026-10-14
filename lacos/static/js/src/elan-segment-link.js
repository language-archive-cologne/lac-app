/**
 * Shareable ELAN segment links (issue #1).
 *
 * A segment link is a W3C Media Fragments anchor appended to a resource's
 * handle URL, carrying a time range:
 *
 *   https://hdl.handle.net/11341/<pid>#t=20.5,24.0
 *
 * Only the time range is used. ELAN renumbers ANNOTATION_IDs on some exports,
 * so annotation ids are not part of a citation; an "id" parameter left over in
 * an older link is ignored.
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
 * @returns {{start: number|null, end: number|null}|null}
 *   null when the hash carries no time range, or when it is malformed.
 */
export function parseSegmentHash(hash) {
  if (typeof hash !== 'string') return null;

  const body = hash.startsWith('#') ? hash.slice(1) : hash;
  if (!body) return null;

  let time = null;

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
    }
  }

  if (!time) return null;

  return { start: time.start, end: time.end };
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
 * A citation is a time range. When the request carries a full [start, end]
 * pair it is authoritative and names *every* row it overlaps — so a link can
 * cite one segment or a whole utterance with the same shape. A point (a bare
 * offset) names a single row, whose bounds then define the range.
 *
 * @param {Array<{id: string, start: number|null, end: number|null}>} rows
 * @param {{start: number|null, end: number|null}|null} parsed
 * @returns {{row: object|null, rows: Array<object>, start: number|null,
 *            end: number|null, matched: boolean}|null}
 *   `rows` is every aligned row overlapping the cited range; `row` is the
 *   first (earliest) of them, or null. `matched` is false when playback should
 *   seek without highlighting a row. null when there is nothing to resolve.
 */
export function resolveSegment(rows, parsed) {
  if (!parsed) return null;

  const { start, end } = parsed;
  if (start === null && end === null) return null;

  let rangeStart = start;
  let rangeEnd = end;
  let anchor = null;

  if (rangeStart === null || rangeEnd === null) {
    // A point names a single row; the anchor's bounds define the range.
    anchor = start !== null ? rowForOffset(rows, start) : null;
    if (anchor) {
      rangeStart = anchor.start;
      rangeEnd = anchor.end;
    } else if (rangeStart === null) {
      // An end-only request, with no start to position on.
      return null;
    }
  }

  const lo = rangeStart === null ? -Infinity : rangeStart;
  const hi = rangeEnd === null ? Infinity : rangeEnd;

  // A full [start, end] pair names every row it overlaps. A point resolved to
  // an anchor names just that row, even when the point also falls inside a
  // wider interval.
  let matchedRows = rows
    .filter((row) => {
      if (!isAligned(row)) return false;
      const rowEnd = typeof row.end === 'number' ? row.end : Infinity;
      return rowEnd > lo && row.start < hi;
    })
    .sort((a, b) => a.start - b.start);
  if (anchor) matchedRows = [anchor];

  return {
    row: matchedRows.length ? matchedRows[0] : anchor,
    rows: matchedRows,
    start: rangeStart,
    end: rangeEnd,
    matched: matchedRows.length > 0,
  };
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
  // Nothing to seek to and nothing to mark, so leave the page as it loaded.
  if (!result.matched && result.start === null) return null;

  if (root && result.start !== null && result.end !== null) {
    root.dispatchEvent(new CustomEvent('elan:selection', {
      bubbles: true,
      detail: { start: result.start, end: result.end, play: false },
    }));
  }

  if (result.start !== null && typeof seek === 'function') {
    seek(result.start, result.end);
  }

  if (result.matched && result.rows.length) {
    const first = result.rows[0];
    result.rows.forEach(({ element }) => {
      element.classList.add(highlightClass);
    });
    if (typeof first.element.scrollIntoView === 'function') {
      first.element.scrollIntoView({ block: 'center', behavior: 'smooth' });
    }
  }

  return result;
}
