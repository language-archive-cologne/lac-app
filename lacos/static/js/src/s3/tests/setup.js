// Mock fetch globally
global.fetch = jest.fn();

// Mock CSRF token
document.body.innerHTML = `
    <input type="hidden" name="csrfmiddlewaretoken" value="test-csrf-token">
`;

// Mock File API
global.File = class {
    constructor(parts, name, options) {
        this.name = name;
        this.type = options.type;
        this.size = parts.length;
        this._parts = parts;
    }

    slice(start, end) {
        const slicedParts = this._parts.slice(start, end);
        return new Blob(slicedParts, { type: this.type });
    }
};

// Mock Blob API
global.Blob = class {
    constructor(parts, options = {}) {
        this.size = parts.length;
        this.type = options.type;
    }
};

// Mock Headers API
global.Headers = class {
    constructor(init) {
        this._headers = new Map();
        if (init) {
            Object.entries(init).forEach(([key, value]) => {
                this._headers.set(key.toLowerCase(), value);
            });
        }
    }

    get(name) {
        return this._headers.get(name.toLowerCase());
    }

    set(name, value) {
        this._headers.set(name.toLowerCase(), value);
    }
}; 