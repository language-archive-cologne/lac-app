/**
 * Tests for shareable ELAN segment links.
 *
 * A segment link is a W3C Media Fragments anchor on a resource's handle URL:
 *
 *   https://hdl.handle.net/11341/<pid>#t=20.5,24.0
 *
 * Only `t` is used: ELAN renumbers ANNOTATION_IDs on some exports, so an `id`
 * left over in an older link is ignored. See issue #1.
 */

/* eslint-env jest */

import {
  parseSegmentHash,
  resolveSegment,
  readAnnotationRows,
  initSegmentLink,
} from '../src/elan-segment-link.js';

// ─── parseSegmentHash ────────────────────────────────────────────────────

describe('parseSegmentHash', () => {
  test('ignores an annotation id left over in an older link', () => {
    expect(parseSegmentHash('#t=20.5,24.0&id=a1')).toEqual({
      start: 20.5,
      end: 24.0,
    });
  });

  test('reads a start-only range as an open-ended segment', () => {
    expect(parseSegmentHash('#t=20.5')).toEqual({
      start: 20.5,
      end: null,
    });
  });

  test('reads a time range', () => {
    expect(parseSegmentHash('#t=20.5,24.0')).toEqual({
      start: 20.5,
      end: 24.0,
    });
  });

  test('accepts the explicit npt: time scheme from the Media Fragments spec', () => {
    expect(parseSegmentHash('#t=npt:20.5,24.0')).toEqual({
      start: 20.5,
      end: 24.0,
    });
  });

  test('reads an end-only range', () => {
    expect(parseSegmentHash('#t=,24.0')).toEqual({
      start: null,
      end: 24.0,
    });
  });

  test('returns null for an annotation id with no time range', () => {
    expect(parseSegmentHash('#id=a1')).toBeNull();
  });

  test('tolerates a missing leading hash', () => {
    expect(parseSegmentHash('t=20.5,24.0')).toEqual({
      start: 20.5,
      end: 24.0,
    });
  });

  test('ignores dimensions it does not understand', () => {
    expect(parseSegmentHash('#t=20.5&track=Source&xywh=0,0,10,10')).toEqual({
      start: 20.5,
      end: null,
    });
  });

  test('returns null for an empty or absent hash', () => {
    expect(parseSegmentHash('')).toBeNull();
    expect(parseSegmentHash('#')).toBeNull();
    expect(parseSegmentHash(null)).toBeNull();
    expect(parseSegmentHash(undefined)).toBeNull();
  });

  test('returns null for a hash carrying no segment dimension', () => {
    expect(parseSegmentHash('#section-metadata')).toBeNull();
  });

  test('returns null when the time range is not a number', () => {
    expect(parseSegmentHash('#t=abc')).toBeNull();
    expect(parseSegmentHash('#t=20.5,abc')).toBeNull();
  });

  test('returns null for a negative start offset', () => {
    expect(parseSegmentHash('#t=-5,10')).toBeNull();
  });

  test('returns null when end precedes start', () => {
    expect(parseSegmentHash('#t=24.0,20.5')).toBeNull();
  });
});

// ─── resolveSegment ──────────────────────────────────────────────────────

describe('resolveSegment', () => {
  // Mirrors what the template emits per row: ELAN ANNOTATION_ID plus offsets.
  const rows = [
    { id: 'a1', start: 0.0, end: 4.2 },
    { id: 'a2', start: 20.5, end: 24.0 },
    { id: 'a3', start: 24.0, end: 29.75 },
  ];

  test('cites a single row when the range spans exactly that row', () => {
    const result = resolveSegment(rows, { start: 20.5, end: 24.0 });

    expect(result.row).toBe(rows[1]);
    expect(result.rows).toEqual([rows[1]]);
    expect(result.start).toBe(20.5);
    expect(result.end).toBe(24.0);
    expect(result.matched).toBe(true);
  });

  test('highlights every row a full range overlaps', () => {
    // An utterance spanning two segments: the cited range is authoritative and
    // names both, so the whole utterance shows, not just the first segment.
    const result = resolveSegment(rows, { start: 21.0, end: 25.5 });

    expect(result.rows).toEqual([rows[1], rows[2]]);
    expect(result.row).toBe(rows[1]);
    expect(result.start).toBe(21.0);
    expect(result.end).toBe(25.5);
    expect(result.matched).toBe(true);
  });

  test('keeps the requested range rather than collapsing to one row', () => {
    const result = resolveSegment(rows, { start: 20.6, end: 29.0 });

    expect(result.start).toBe(20.6);
    expect(result.end).toBe(29.0);
    expect(result.rows).toEqual([rows[1], rows[2]]);
  });




  test('matches the row whose interval contains a hand-written offset', () => {
    // "#t=22" — a human citing a moment, not an exact segment boundary.
    const result = resolveSegment(rows, { start: 22, end: null });

    expect(result.rows).toEqual([rows[1]]);
    expect(result.start).toBe(20.5);
    expect(result.end).toBe(24.0);
  });

  test('prefers an exact row for a point over a containing interval', () => {
    const overlapping = [
      { id: 'wide', start: 18.0, end: 30.0 },
      { id: 'exact', start: 20.5, end: 24.0 },
    ];

    const result = resolveSegment(overlapping, { start: 20.5, end: null });

    expect(result.rows).toEqual([overlapping[1]]);
  });

  test('seeks without highlighting when no row matches the time range', () => {
    const result = resolveSegment(rows, { start: 90.0, end: 95.0 });

    expect(result.row).toBeNull();
    expect(result.rows).toEqual([]);
    expect(result.start).toBe(90.0);
    expect(result.end).toBe(95.0);
    expect(result.matched).toBe(false);
  });

  test('tolerates millisecond rounding in the emitted offsets', () => {
    const result = resolveSegment(rows, { start: 20.5004, end: 24.0 });

    expect(result.row).toBe(rows[1]);
  });

  test('returns null when there is nothing to resolve', () => {
    expect(resolveSegment(rows, null)).toBeNull();
    expect(resolveSegment(rows, { start: null, end: null })).toBeNull();
  });


  test('returns null when the table has no rows', () => {
    expect(resolveSegment([], { start: 20.5, end: 24.0 })).toEqual({
      row: null,
      rows: [],
      start: 20.5,
      end: 24.0,
      matched: false,
    });
  });
});

// ─── readAnnotationRows ──────────────────────────────────────────────────

describe('readAnnotationRows', () => {
  const build = (bodyHtml) => {
    const root = document.createElement('div');
    root.innerHTML = `<table><tbody>${bodyHtml}</tbody></table>`;
    return root;
  };

  test('reads id and offsets from the rendered rows', () => {
    const root = build(`
      <tr id="ann-a1" data-annotation-id="a1"
          data-annotation-start="0.000" data-annotation-end="4.200"></tr>
      <tr id="ann-a2" data-annotation-id="a2"
          data-annotation-start="20.500" data-annotation-end="24.000"></tr>
    `);

    const rows = readAnnotationRows(root);

    expect(rows).toHaveLength(2);
    expect(rows[1]).toMatchObject({ id: 'a2', start: 20.5, end: 24.0 });
    expect(rows[1].element).toBe(root.querySelector('#ann-a2'));
  });

  test('reports an unaligned row with null offsets', () => {
    const root = build('<tr id="ann-a9" data-annotation-id="a9"></tr>');

    expect(readAnnotationRows(root)[0]).toMatchObject({
      id: 'a9',
      start: null,
      end: null,
    });
  });

  test('returns an empty list when there is no annotation table', () => {
    expect(readAnnotationRows(document.createElement('div'))).toEqual([]);
  });
});

// ─── initSegmentLink ─────────────────────────────────────────────────────

describe('initSegmentLink', () => {
  let root;
  let seek;

  beforeEach(() => {
    // jsdom does not implement scrollIntoView.
    Element.prototype.scrollIntoView = jest.fn();
    seek = jest.fn();
    root = document.createElement('div');
    root.innerHTML = `
      <table><tbody>
        <tr id="ann-a1" data-annotation-id="a1"
            data-annotation-start="0.000" data-annotation-end="4.200"></tr>
        <tr id="ann-a2" data-annotation-id="a2"
            data-annotation-start="20.500" data-annotation-end="24.000"></tr>
      </tbody></table>
    `;
  });

  test('seeks to the segment start and highlights the matched row', () => {
    const result = initSegmentLink(root, { hash: '#t=20.5,24.0', seek });

    expect(seek).toHaveBeenCalledWith(20.5, 24.0);
    expect(root.querySelector('#ann-a2').classList.contains('bg-blue-100')).toBe(true);
    expect(result.matched).toBe(true);
  });

  test('scrolls the matched row into view', () => {
    initSegmentLink(root, { hash: '#t=20.5,24.0', seek });

    expect(root.querySelector('#ann-a2').scrollIntoView).toHaveBeenCalled();
  });

  test('leaves other rows unhighlighted', () => {
    initSegmentLink(root, { hash: '#t=20.5,24.0', seek });

    expect(root.querySelector('#ann-a1').classList.contains('bg-blue-100')).toBe(false);
  });

  test('seeks without highlighting when no row matches', () => {
    const result = initSegmentLink(root, { hash: '#t=90.0,95.0', seek });

    expect(seek).toHaveBeenCalledWith(90.0, 95.0);
    expect(root.querySelectorAll('.bg-blue-100')).toHaveLength(0);
    expect(result.matched).toBe(false);
  });


  test('does nothing when the hash carries no segment', () => {
    const result = initSegmentLink(root, { hash: '#section-metadata', seek });

    expect(result).toBeNull();
    expect(seek).not.toHaveBeenCalled();
    expect(root.querySelectorAll('.bg-blue-100')).toHaveLength(0);
  });


  test('honours a caller-supplied highlight class', () => {
    initSegmentLink(root, { hash: '#t=20.5', seek, highlightClass: 'ring' });

    expect(root.querySelector('#ann-a2').classList.contains('ring')).toBe(true);
  });
});
