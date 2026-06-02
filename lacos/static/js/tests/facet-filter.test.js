/* eslint-env jest */

import { bindFacetFilters, filterFacetValues } from '../src/facet-filter.js';

function facetMarkup() {
  return `
    <div data-facet-filter-scope>
      <input data-facet-filter-input>
      <a data-facet-label="Phonology"></a>
      <a data-facet-label="Lexicon"></a>
      <a data-facet-label="Narrative texts"></a>
    </div>
  `;
}

describe('facet-filter', () => {
  beforeEach(() => {
    document.body.innerHTML = facetMarkup();
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  test('filters facet values case-insensitively', () => {
    const input = document.querySelector('[data-facet-filter-input]');
    input.value = 'PHON';

    filterFacetValues(input);

    expect(document.querySelector('[data-facet-label="Phonology"]').hidden).toBe(false);
    expect(document.querySelector('[data-facet-label="Lexicon"]').hidden).toBe(true);
    expect(document.querySelector('[data-facet-label="Narrative texts"]').hidden).toBe(true);
  });

  test('empty filter restores all facet values', () => {
    const input = document.querySelector('[data-facet-filter-input]');
    input.value = 'lex';
    filterFacetValues(input);

    input.value = '';
    filterFacetValues(input);

    document.querySelectorAll('[data-facet-label]').forEach((item) => {
      expect(item.hidden).toBe(false);
    });
  });

  test('delegated input binding handles dynamically swapped facet markup', () => {
    document.body.innerHTML = '<main id="root"></main>';
    const root = document.getElementById('root');
    const unbind = bindFacetFilters(root);
    root.innerHTML = facetMarkup();
    const input = root.querySelector('[data-facet-filter-input]');

    input.value = 'text';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    expect(root.querySelector('[data-facet-label="Narrative texts"]').hidden).toBe(false);
    expect(root.querySelector('[data-facet-label="Phonology"]').hidden).toBe(true);
    expect(root.querySelector('[data-facet-label="Lexicon"]').hidden).toBe(true);

    unbind();
  });
});
