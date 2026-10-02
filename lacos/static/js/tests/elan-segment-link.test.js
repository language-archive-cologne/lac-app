/**
 * Tests for shareable ELAN segment links.
 *
 * A segment link is a W3C Media Fragments anchor on a resource's handle URL:
 *
 *   https://hdl.handle.net/11341/<pid>#t=20.5,24.0&id=a1
 *
 * `t` is authoritative; `id` (the ELAN ANNOTATION_ID) is an advisory hint that
 * can sharpen the link but must never misdirect it. See issue #1.
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
  test('reads a time range and an annotation id', () => {
    expect(parseSegmentHash('#t=20.5,24.0&id=a1')).toEqual({
      start: 20.5,
      end: 24.0,
      id: 'a1',
    });
  });

  test('reads a start-only range as an open-ended segment', () => {
    expect(parseSegmentHash('#t=20.5')).toEqual({
      start: 20.5,
      end: null,
      id: null,
    });
  });

  test('reads a time range without an annotation id', () => {
    expect(parseSegmentHash('#t=20.5,24.0')).toEqual({
      start: 20.5,
      end: 24.0,
      id: null,
    });
  });

  test('accepts the explicit npt: time scheme from the Media Fragments spec', () => {
    expect(parseSegmentHash('#t=npt:20.5,24.0')).toEqual({
      start: 20.5,
      end: 24.0,
      id: null,
    });
  });

  test('reads an end-only range', () => {
    expect(parseSegmentHash('#t=,24.0')).toEqual({
      start: null,
      end: 24.0,
      id: null,
    });
  });

  test('reads an annotation id with no time range', () => {
    expect(parseSegmentHash('#id=a1')).toEqual({
      start: null,
      end: null,
      id: 'a1',
    });
  });

  test('tolerates a missing leading hash', () => {
    expect(parseSegmentHash('t=20.5,24.0&id=a1')).toEqual({
      start: 20.5,
      end: 24.0,
      id: 'a1',
    });
  });

  test('ignores dimensions it does not understand', () => {
    expect(parseSegmentHash('#t=20.5&track=Source&xywh=0,0,10,10')).toEqual({
      start: 20.5,
      end: null,
      id: null,
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

  test('uses the annotation id when it agrees with the time range', () => {
    const result = resolveSegment(rows, { start: 20.5, end: 24.0, id: 'a2' });

    expect(result).toEqual({ row: rows[1], start: 20.5, end: 24.0, matched: true });
  });

  test('uses the annotation id alone when no time range is given', () => {
    const result = resolveSegment(rows, { start: null, end: null, id: 'a3' });

    expect(result).toEqual({ row: rows[2], start: 24.0, end: 29.75, matched: true });
  });

  test('ignores a stale annotation id and falls back to the time range', () => {
    // The .eaf was re-exported and ANNOTATION_IDs were renumbered: a2 now
    // names a different interval than the one the link was made for.
    const result = resolveSegment(rows, { start: 24.0, end: 29.75, id: 'a2' });

    expect(result).toEqual({ row: rows[2], start: 24.0, end: 29.75, matched: true });
  });

  test('ignores an annotation id that is absent from the table', () => {
    const result = resolveSegment(rows, { start: 20.5, end: 24.0, id: 'nope' });

    expect(result).toEqual({ row: rows[1], start: 20.5, end: 24.0, matched: true });
  });

  test('matches a row by time range when no id is given', () => {
    const result = resolveSegment(rows, { start: 20.5, end: 24.0, id: null });

    expect(result).toEqual({ row: rows[1], start: 20.5, end: 24.0, matched: true });
  });

  test('matches the row whose interval contains a hand-written offset', () => {
    // "#t=22" — a human citing a moment, not an exact segment boundary.
    const result = resolveSegment(rows, { start: 22, end: null, id: null });

    expect(result).toEqual({ row: rows[1], start: 20.5, end: 24.0, matched: true });
  });

  test('prefers an exact start match over a containing interval', () => {
    const overlapping = [
      { id: 'wide', start: 18.0, end: 30.0 },
      { id: 'exact', start: 20.5, end: 24.0 },
    ];

    const result = resolveSegment(overlapping, { start: 20.5, end: 24.0, id: null });

    expect(result.row).toBe(overlapping[1]);
  });

  test('seeks without highlighting when no row matches the time range', () => {
    const result = resolveSegment(rows, { start: 90.0, end: 95.0, id: null });

    expect(result).toEqual({ row: null, start: 90.0, end: 95.0, matched: false });
  });

  test('tolerates millisecond rounding in the emitted offsets', () => {
    const result = resolveSegment(rows, { start: 20.5004, end: 24.0, id: null });

    expect(result.row).toBe(rows[1]);
  });

  test('returns null when there is nothing to resolve', () => {
    expect(resolveSegment(rows, null)).toBeNull();
    expect(resolveSegment(rows, { start: null, end: null, id: null })).toBeNull();
  });

  test('returns null when the table has no rows', () => {
    expect(resolveSegment([], { start: 20.5, end: 24.0, id: 'a2' })).toEqual({
      row: null,
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
    const result = initSegmentLink(root, { hash: '#t=20.5,24.0&id=a2', seek });

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

  test('falls back to the time range when the annotation id is stale', () => {
    // Link says a2, but a2 in this file spans a different interval.
    const result = initSegmentLink(root, { hash: '#t=0.0,4.2&id=a2', seek });

    expect(result.row.id).toBe('a1');
    expect(seek).toHaveBeenCalledWith(0.0, 4.2);
  });

  test('does nothing when the hash carries no segment', () => {
    const result = initSegmentLink(root, { hash: '#section-metadata', seek });

    expect(result).toBeNull();
    expect(seek).not.toHaveBeenCalled();
    expect(root.querySelectorAll('.bg-blue-100')).toHaveLength(0);
  });

  test('does not seek for an id-only link that matches no row', () => {
    const result = initSegmentLink(root, { hash: '#id=gone', seek });

    expect(result).toBeNull();
    expect(seek).not.toHaveBeenCalled();
  });

  test('honours a caller-supplied highlight class', () => {
    initSegmentLink(root, { hash: '#t=20.5', seek, highlightClass: 'ring' });

    expect(root.querySelector('#ann-a2').classList.contains('ring')).toBe(true);
  });
});
