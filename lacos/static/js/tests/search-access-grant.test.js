/* eslint-env jest */

import {
  acquireGrant,
  bindSearchAccess,
  ensureGrant,
  getSearchAccessConfig,
  handleVerificationRejection,
  primeSearchAccess,
  resetSearchAccessState,
} from '../src/search/search-access-grant.js';

function configMarkup({ grantNeeded = '1' } = {}) {
  return `
    <div id="search-access-config"
         hidden
         data-grant-needed="${grantNeeded}"
         data-challenge-url="/storage/altcha/challenge/"
         data-grant-url="/search-access/"
         data-csrf-token="test-csrf-token"></div>
  `;
}

function autoSolveWidgets(payload = 'solved-payload') {
  // jsdom has no real <altcha-widget>; emit "verified" as soon as one is added.
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.tagName === 'ALTCHA-WIDGET') {
          node.dispatchEvent(
            new CustomEvent('verified', { detail: { payload } }),
          );
        }
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
  return observer;
}

function failingWidgets() {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      mutation.addedNodes.forEach((node) => {
        if (node.tagName === 'ALTCHA-WIDGET') {
          node.dispatchEvent(
            new CustomEvent('statechange', { detail: { state: 'error' } }),
          );
        }
      });
    });
  });
  observer.observe(document.body, { childList: true, subtree: true });
  return observer;
}

function flushPromises() {
  return new Promise((resolve) => setTimeout(resolve, 0));
}

describe('search-access-grant', () => {
  let widgetObserver;

  beforeEach(() => {
    document.body.innerHTML = configMarkup();
    resetSearchAccessState();
    global.fetch = jest.fn().mockResolvedValue({ status: 204 });
    window.htmx = { ajax: jest.fn().mockResolvedValue(undefined) };
  });

  afterEach(() => {
    if (widgetObserver) {
      widgetObserver.disconnect();
      widgetObserver = null;
    }
    document.body.innerHTML = '';
    delete global.fetch;
    delete window.htmx;
  });

  test('reads config from the DOM', () => {
    const config = getSearchAccessConfig();
    expect(config.grantNeeded).toBe(true);
    expect(config.challengeUrl).toBe('/storage/altcha/challenge/');
    expect(config.grantUrl).toBe('/search-access/');
    expect(config.csrfToken).toBe('test-csrf-token');
  });

  test('acquireGrant posts the solved payload in inline mode', async () => {
    widgetObserver = autoSolveWidgets('the-payload');
    const config = getSearchAccessConfig();

    await acquireGrant(config);

    expect(global.fetch).toHaveBeenCalledTimes(1);
    const [url, options] = global.fetch.mock.calls[0];
    expect(url).toBe('/search-access/');
    expect(options.method).toBe('POST');
    expect(options.credentials).toBe('same-origin');
    expect(options.body.get('altcha')).toBe('the-payload');
    expect(options.body.get('mode')).toBe('inline');
    expect(options.body.get('csrfmiddlewaretoken')).toBe('test-csrf-token');
    expect(config.host.dataset.grantNeeded).toBe('0');
    expect(document.querySelector('altcha-widget')).toBeNull();
  });

  test('acquireGrant rejects when the grant endpoint refuses', async () => {
    widgetObserver = autoSolveWidgets();
    global.fetch.mockResolvedValue({ status: 403 });
    const config = getSearchAccessConfig();

    await expect(acquireGrant(config)).rejects.toThrow('status 403');
    expect(config.host.dataset.grantNeeded).toBe('1');
  });

  test('acquireGrant rejects when the challenge errors', async () => {
    widgetObserver = failingWidgets();
    const config = getSearchAccessConfig();

    await expect(acquireGrant(config)).rejects.toThrow('ALTCHA challenge failed');
    expect(global.fetch).not.toHaveBeenCalled();
  });

  test('ensureGrant deduplicates concurrent verifications', async () => {
    widgetObserver = autoSolveWidgets();
    const config = getSearchAccessConfig();

    await Promise.all([ensureGrant(config), ensureGrant(config)]);

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('primeSearchAccess solves in the background when a grant is needed', async () => {
    widgetObserver = autoSolveWidgets();

    await primeSearchAccess();

    expect(global.fetch).toHaveBeenCalledTimes(1);
  });

  test('primeSearchAccess is a no-op when the grant already exists', () => {
    document.body.innerHTML = configMarkup({ grantNeeded: '0' });

    expect(primeSearchAccess()).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });

  function verificationEvent(elt, { status = 403, header = 'required' } = {}) {
    return new CustomEvent('htmx:beforeOnLoad', {
      cancelable: true,
      detail: {
        elt,
        xhr: {
          status,
          getResponseHeader: (name) =>
            name === 'X-Search-Verification' ? header : null,
        },
        pathInfo: { finalRequestPath: '/search/?language=yua' },
      },
    });
  }

  test('re-verifies and replays a rejected HTMX search inline', async () => {
    widgetObserver = autoSolveWidgets();
    const elt = document.createElement('a');
    document.body.appendChild(elt);

    const event = verificationEvent(elt);
    handleVerificationRejection(event);

    expect(event.defaultPrevented).toBe(true);
    await flushPromises();
    expect(window.htmx.ajax).toHaveBeenCalledWith('GET', '/search/?language=yua', {
      source: elt,
    });
    expect(elt.dataset.searchAccessRetried).toBeUndefined();
  });

  test('lets HX-Redirect proceed when the inline retry is rejected again', () => {
    const elt = document.createElement('a');
    elt.dataset.searchAccessRetried = '1';
    document.body.appendChild(elt);

    const event = verificationEvent(elt);
    handleVerificationRejection(event);

    expect(event.defaultPrevented).toBe(false);
    expect(elt.dataset.searchAccessRetried).toBeUndefined();
  });

  test('ignores 403 responses without the verification marker header', () => {
    const elt = document.createElement('a');
    document.body.appendChild(elt);

    const event = verificationEvent(elt, { header: null });
    handleVerificationRejection(event);

    expect(event.defaultPrevented).toBe(false);
  });

  test('falls back to the interstitial when inline verification fails', async () => {
    widgetObserver = failingWidgets();
    const assign = jest.fn();
    const originalLocation = window.location;
    delete window.location;
    window.location = { ...originalLocation, assign };
    const elt = document.createElement('a');
    document.body.appendChild(elt);

    const event = verificationEvent(elt);
    handleVerificationRejection(event);

    expect(event.defaultPrevented).toBe(true);
    await flushPromises();
    expect(assign).toHaveBeenCalledWith(
      '/search-access/?next=%2Fsearch%2F%3Flanguage%3Dyua',
    );
    window.location = originalLocation;
  });

  test('bindSearchAccess listens for rejections and primes the grant', async () => {
    widgetObserver = autoSolveWidgets();

    const unbind = bindSearchAccess();
    await flushPromises();
    expect(global.fetch).toHaveBeenCalledTimes(1);

    const elt = document.createElement('a');
    document.body.appendChild(elt);
    const event = verificationEvent(elt);
    document.body.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    unbind();
  });
});
