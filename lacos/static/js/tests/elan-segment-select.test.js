/**
 * Tests for the multi-segment range citation (see issue #1 follow-up).
 */

/* eslint-env jest */

import {
  buildRangeAnchor,
  initElanSegmentSelect,
} from '../src/elan-segment-select.js';

// ─── buildRangeAnchor ────────────────────────────────────────────────────

describe('buildRangeAnchor', () => {
  test('spans the union of several segments', () => {
    expect(
      buildRangeAnchor([
        [56.22, 56.97],
        [57.67, 59.21],
        [58.235, 58.505],
      ]),
    ).toBe('#t=56.220,59.210');
  });

  test('emits the same shape as a single-segment link for one segment', () => {
    expect(buildRangeAnchor([[20.5, 24.0]])).toBe('#t=20.500,24.000');
  });

  test('ignores unaligned segments without bounds', () => {
    expect(
      buildRangeAnchor([
        [NaN, 5],
        [20.5, 24.0],
      ]),
    ).toBe('#t=20.500,24.000');
  });

  test('drops degenerate spans with end <= start', () => {
    expect(buildRangeAnchor([[24.0, 24.0]])).toBeNull();
  });

  test('returns null for an empty selection', () => {
    expect(buildRangeAnchor([])).toBeNull();
  });
});

// ─── initElanSegmentSelect ───────────────────────────────────────────────

describe('initElanSegmentSelect', () => {
  function buildScope() {
    const scope = document.createElement('div');
    scope.setAttribute('data-elan-scope', '');
    scope.setAttribute('data-segment-link-base', 'https://hdl.handle.net/11341/x');
    scope.innerHTML = `
      <div data-elan-range-bar class="hidden">
        <span data-range-count>0 segments</span>
        <button data-copy-text=""></button>
        <button data-elan-range-clear></button>
      </div>
      <table>
        <tbody>
          <tr data-annotation-id="a1"><td>
            <input type="checkbox" class="elan-segment-check"
                   data-annotation-start="56.220" data-annotation-end="56.970" />
          </td></tr>
          <tr data-annotation-id="a2"><td>
            <input type="checkbox" class="elan-segment-check"
                   data-annotation-start="57.670" data-annotation-end="59.210" />
          </td></tr>
        </tbody>
      </table>
    `;
    return scope;
  }

  function check(scope, index) {
    const box = scope.querySelectorAll('input.elan-segment-check')[index];
    box.checked = true;
    box.dispatchEvent(new Event('change', { bubbles: true }));
    return box;
  }

  test('stays hidden below two selected segments', () => {
    const scope = buildScope();
    document.body.appendChild(scope);
    initElanSegmentSelect(scope);
    const bar = scope.querySelector('[data-elan-range-bar]');

    check(scope, 0);

    expect(bar.classList.contains('hidden')).toBe(true);
    document.body.removeChild(scope);
  });

  test('shows the bar and offers the full range URL from two segments on', () => {
    const scope = buildScope();
    document.body.appendChild(scope);
    initElanSegmentSelect(scope);
    const bar = scope.querySelector('[data-elan-range-bar]');
    const copy = scope.querySelector('[data-copy-text]');

    check(scope, 0);
    check(scope, 1);

    expect(bar.classList.contains('hidden')).toBe(false);
    expect(copy.dataset.copyText).toBe(
      'https://hdl.handle.net/11341/x#t=56.220,59.210',
    );
    document.body.removeChild(scope);
  });

  test('clears the selection and hides the bar again', () => {
    const scope = buildScope();
    document.body.appendChild(scope);
    initElanSegmentSelect(scope);
    const bar = scope.querySelector('[data-elan-range-bar]');

    check(scope, 0);
    check(scope, 1);
    scope.querySelector('[data-elan-range-clear]').click();

    expect(
      [...scope.querySelectorAll('input.elan-segment-check')].every(
        (box) => !box.checked,
      ),
    ).toBe(true);
    expect(bar.classList.contains('hidden')).toBe(true);
    document.body.removeChild(scope);
  });

  test('is idempotent', () => {
    const scope = buildScope();
    document.body.appendChild(scope);
    initElanSegmentSelect(scope);
    initElanSegmentSelect(scope); // must not throw or double-wire

    const box = scope.querySelectorAll('input.elan-segment-check')[0];
    box.checked = true;
    expect(
      scope.querySelector('[data-elan-range-bar]').classList.contains('hidden'),
    ).toBe(true);
    document.body.removeChild(scope);
  });
});
