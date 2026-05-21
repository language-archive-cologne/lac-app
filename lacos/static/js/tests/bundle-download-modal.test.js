/* eslint-env jest */

import { BundleDownloadModal } from '../src/download/bundle-download-modal.js';

function modalMarkup({ packageMaxBytes = 524288000 } = {}) {
    return `
        <dialog id="bundle-download-modal" data-package-max-bytes="${packageMaxBytes}">
            <h3 id="bundle-download-title"></h3>
            <input type="hidden" name="csrfmiddlewaretoken" value="csrf-token">
            <div id="bundle-download-summary"></div>
            <span id="bundle-download-count"></span>
            <span id="bundle-download-total-size"></span>
            <p id="bundle-download-name"></p>
            <div id="bundle-download-methods">
                <button type="button" class="tab tab-active" data-download-tab="package"></button>
                <button type="button" class="tab" data-download-tab="scripts"></button>
                <div id="bundle-package-panel" data-download-panel="package">
                    <button id="btn-start-package" type="button"></button>
                    <button id="btn-package-limit-use-scripts" type="button"></button>
                </div>
                <div id="bundle-scripts-panel" data-download-panel="scripts" class="hidden">
                    <div id="bundle-package-disabled-note" class="hidden"></div>
                    <button id="btn-start-scripts" type="button"></button>
                </div>
            </div>
            <div id="bundle-altcha-container">
                <p id="bundle-altcha-text"></p>
                <div id="bundle-altcha-widget"></div>
            </div>
            <div id="bundle-download-loading" class="hidden">
                <span id="bundle-loading-message"></span>
            </div>
            <div id="bundle-download-error" class="hidden">
                <span id="bundle-error-message"></span>
            </div>
            <div id="bundle-package-result" class="hidden">
                <span id="bundle-package-message"></span>
                <button id="btn-package-use-scripts" type="button"></button>
            </div>
            <div id="bundle-script-options" class="hidden">
                <div id="bundle-skipped-warning" class="hidden">
                    <span id="bundle-skipped-message"></span>
                    <ul id="bundle-skipped-reasons"></ul>
                </div>
                <strong id="bundle-expires-at"></strong>
                <div id="bundle-script-output-tabs">
                    <button type="button" class="tab tab-active" data-script-tab="powershell"></button>
                    <button type="button" class="tab" data-script-tab="bash"></button>
                    <button type="button" class="tab" data-script-tab="manifest"></button>
                    <button type="button" class="tab" data-script-tab="commands"></button>
                </div>
                <div data-script-panel="powershell">
                    <button id="btn-download-powershell" type="button"></button>
                    <button id="btn-copy-powershell-command" type="button"></button>
                </div>
                <div data-script-panel="bash" class="hidden">
                    <button id="btn-download-bash" type="button"></button>
                    <button id="btn-copy-bash-command" type="button"></button>
                </div>
                <div data-script-panel="manifest" class="hidden">
                    <button id="btn-download-manifest" type="button"></button>
                </div>
                <div data-script-panel="commands" class="hidden">
                    <button id="btn-copy-curl" type="button"></button>
                    <div id="bundle-file-commands"></div>
                </div>
            </div>
        </dialog>
    `;
}

function makeModal(markupOptions = {}) {
    document.body.innerHTML = modalMarkup(markupOptions);
    const modal = document.getElementById('bundle-download-modal');
    modal.showModal = jest.fn();
    modal.close = jest.fn();
    const widget = document.getElementById('bundle-altcha-widget');
    widget.reset = jest.fn();
    widget.verify = jest.fn();

    return new BundleDownloadModal(modal, {
        challengeUrl: '/challenge/',
        scriptsUrl: '/scripts/',
        packageUrl: '/package/',
    });
}

function dispatchVerified(payload = 'verified-payload') {
    const widget = document.getElementById('bundle-altcha-widget');
    widget.dispatchEvent(new CustomEvent('verified', { detail: { payload } }));
}

describe('BundleDownloadModal', () => {
    let clickSpy;

    beforeEach(() => {
        jest.clearAllMocks();
        global.fetch = jest.fn();
        global.URL.createObjectURL = jest.fn(() => 'blob:package');
        global.URL.revokeObjectURL = jest.fn();
        Object.defineProperty(navigator, 'clipboard', {
            value: { writeText: jest.fn().mockResolvedValue(undefined) },
            configurable: true,
        });
        clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    });

    afterEach(() => {
        clickSpy.mockRestore();
    });

    test('downloads a package by default after verification', async () => {
        const modal = makeModal();
        fetch.mockResolvedValue({
            ok: true,
            headers: {
                get: (name) => name.toLowerCase() === 'content-disposition'
                    ? 'attachment; filename="Bundle.tar"'
                    : 'application/x-tar',
            },
            blob: jest.fn().mockResolvedValue(new Blob(['tar'], { type: 'application/x-tar' })),
        });

        modal.open('bundle-1', ['res-1', 'res-2'], 'Bundle');
        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(fetch).toHaveBeenCalledWith('/package/', expect.objectContaining({ method: 'POST' }));
        expect(fetch).not.toHaveBeenCalledWith('/scripts/', expect.anything());
        expect(fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('csrf-token');
        expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
            altcha: 'verified-payload',
            bundle_id: 'bundle-1',
            resource_ids: ['res-1', 'res-2'],
        });
        expect(clickSpy).toHaveBeenCalled();
        expect(document.getElementById('bundle-package-result').classList.contains('hidden')).toBe(false);
    });

    test('generates scripts when the script method is selected', async () => {
        const modal = makeModal();
        fetch.mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue({
                expires_at: '2026-05-20T12:00:00Z',
                file_count: 1,
                scripts: {
                    bash: '#!/bin/bash',
                    powershell: '# PowerShell',
                    manifest: {
                        files: [{ filename: 'file.wav', url: 'https://example.test/file.wav' }],
                    },
                },
                total_size: 2048,
                errors: [],
            }),
        });

        modal.open('bundle-1', ['res-1'], 'Bundle');
        document.querySelector('[data-download-tab="scripts"]').click();
        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(fetch).toHaveBeenCalledWith('/scripts/', expect.objectContaining({ method: 'POST' }));
        expect(fetch.mock.calls[0][1].headers['X-CSRFToken']).toBe('csrf-token');
        expect(JSON.parse(fetch.mock.calls[0][1].body)).toEqual({
            altcha: 'verified-payload',
            bundle_id: 'bundle-1',
            resource_ids: ['res-1'],
        });
        expect(document.getElementById('bundle-script-options').classList.contains('hidden')).toBe(false);
        expect(document.getElementById('bundle-download-total-size').textContent).toBe('2 KB');
    });

    test('package size warning button switches directly to scripts', () => {
        const modal = makeModal();
        modal.open('bundle-1', ['res-1'], 'Bundle');

        document.getElementById('btn-package-limit-use-scripts').click();

        expect(modal.selectedMethod).toBe('scripts');
        expect(document.querySelector('[data-download-tab="scripts"]').classList.contains('tab-active')).toBe(true);
        expect(document.querySelector('[data-download-tab="scripts"]').classList.contains('bg-primary')).toBe(true);
        expect(document.querySelector('[data-download-tab="package"]').classList.contains('bg-base-100')).toBe(true);
        expect(document.getElementById('bundle-scripts-panel').classList.contains('hidden')).toBe(false);
        expect(document.getElementById('bundle-package-panel').classList.contains('hidden')).toBe(true);
    });

    test('oversized selections disable package downloads and default to scripts', async () => {
        const modal = makeModal({ packageMaxBytes: 1024 });
        fetch.mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue({
                expires_at: '2026-05-20T12:00:00Z',
                file_count: 1,
                scripts: { manifest: { files: [] } },
                errors: [],
            }),
        });

        modal.open('bundle-1', ['res-1'], 'Bundle', { totalSizeBytes: 2048 });

        expect(modal.selectedMethod).toBe('scripts');
        expect(document.querySelector('[data-download-tab="package"]').disabled).toBe(true);
        expect(document.getElementById('btn-start-package').disabled).toBe(true);
        expect(document.getElementById('bundle-package-disabled-note').classList.contains('hidden')).toBe(false);
        expect(document.getElementById('bundle-scripts-panel').classList.contains('hidden')).toBe(false);

        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(fetch).toHaveBeenCalledWith('/scripts/', expect.objectContaining({ method: 'POST' }));
        expect(fetch).not.toHaveBeenCalledWith('/package/', expect.anything());
    });

    test('shows selected total size in the modal summary', () => {
        const modal = makeModal();

        modal.open('bundle-1', ['res-1', 'res-2'], 'Bundle', { totalSizeBytes: 1536 });

        expect(document.getElementById('bundle-download-count').textContent).toBe('2');
        expect(document.getElementById('bundle-download-total-size').textContent).toBe('1.5 KB');
        expect(document.getElementById('bundle-download-name').textContent).toBe('Bundle');
    });

    test('package action prompts verification without changing the selected download tab', () => {
        const modal = makeModal();
        modal.open('bundle-1', ['res-1'], 'Bundle');

        document.getElementById('btn-start-package').click();

        expect(document.getElementById('bundle-altcha-widget').verify).toHaveBeenCalled();
        expect(document.querySelector('[data-download-tab="package"]').classList.contains('tab-active')).toBe(true);
        expect(document.getElementById('bundle-package-panel').classList.contains('hidden')).toBe(false);
    });

    test('script output tabs show one script option at a time', async () => {
        const modal = makeModal();
        fetch.mockResolvedValue({
            ok: true,
            json: jest.fn().mockResolvedValue({
                expires_at: '2026-05-20T12:00:00Z',
                file_count: 1,
                scripts: {
                    bash: '#!/bin/bash',
                    powershell: '# PowerShell',
                    manifest: {
                        files: [{ filename: 'file.wav', url: 'https://example.test/file.wav' }],
                    },
                },
                errors: [],
            }),
        });

        modal.open('bundle-1', ['res-1'], 'Bundle');
        document.querySelector('[data-download-tab="scripts"]').click();
        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(document.querySelector('[data-script-panel="powershell"]').classList.contains('hidden')).toBe(false);
        expect(document.querySelector('[data-script-panel="bash"]').classList.contains('hidden')).toBe(true);

        document.querySelector('[data-script-tab="bash"]').click();

        expect(document.querySelector('[data-script-panel="powershell"]').classList.contains('hidden')).toBe(true);
        expect(document.querySelector('[data-script-panel="bash"]').classList.contains('hidden')).toBe(false);
    });

    test('script tabs copy safe local run commands', async () => {
        const modal = makeModal();
        modal._showCopyFeedback = jest.fn();

        document.getElementById('btn-copy-powershell-command').click();
        await Promise.resolve();

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('.\\download.ps1');

        document.getElementById('btn-copy-bash-command').click();
        await Promise.resolve();

        expect(navigator.clipboard.writeText).toHaveBeenCalledWith('bash download.sh');
        expect(modal._showCopyFeedback).toHaveBeenCalledTimes(2);
    });

    test('switching from package result to scripts preserves the selected resources', async () => {
        const modal = makeModal();
        fetch
            .mockResolvedValueOnce({
                ok: true,
                headers: {
                    get: () => 'attachment; filename="Bundle.tar"',
                },
                blob: jest.fn().mockResolvedValue(new Blob(['tar'], { type: 'application/x-tar' })),
            })
            .mockResolvedValueOnce({
                ok: true,
                json: jest.fn().mockResolvedValue({
                    expires_at: '2026-05-20T12:00:00Z',
                    file_count: 1,
                    scripts: { manifest: { files: [] } },
                    errors: [],
                }),
            });

        modal.open('bundle-1', ['res-1'], 'Bundle');
        dispatchVerified('package-payload');
        await Promise.resolve();
        await Promise.resolve();

        document.getElementById('btn-package-use-scripts').click();
        dispatchVerified('scripts-payload');
        await Promise.resolve();
        await Promise.resolve();

        expect(fetch.mock.calls[1][0]).toBe('/scripts/');
        expect(JSON.parse(fetch.mock.calls[1][1].body)).toEqual({
            altcha: 'scripts-payload',
            bundle_id: 'bundle-1',
            resource_ids: ['res-1'],
        });
    });

    test('uses RFC 5987 filename from package response when present', async () => {
        const modal = makeModal();
        fetch.mockResolvedValue({
            ok: true,
            headers: {
                get: (name) => name.toLowerCase() === 'content-disposition'
                    ? "attachment; filename=\"Bundle.tar\"; filename*=UTF-8''B%C3%BCndle.tar"
                    : 'application/x-tar',
            },
            blob: jest.fn().mockResolvedValue(new Blob(['tar'], { type: 'application/x-tar' })),
        });

        modal.open('bundle-1', ['res-1'], 'Bundle');
        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(document.getElementById('bundle-package-message').textContent).toContain('Bündle.tar');
    });

    test('shows skipped count after partial package download', async () => {
        const modal = makeModal();
        fetch.mockResolvedValue({
            ok: true,
            headers: {
                get: (name) => {
                    if (name.toLowerCase() === 'content-disposition') return 'attachment; filename="Bundle.tar"';
                    if (name.toLowerCase() === 'x-download-skipped-count') return '2';
                    return 'application/x-tar';
                },
            },
            blob: jest.fn().mockResolvedValue(new Blob(['tar'], { type: 'application/x-tar' })),
        });

        modal.open('bundle-1', ['res-1', 'res-2', 'res-3'], 'Bundle');
        dispatchVerified();
        await Promise.resolve();
        await Promise.resolve();

        expect(document.getElementById('bundle-package-message').textContent)
            .toContain('2 files could not be included');
    });
});
