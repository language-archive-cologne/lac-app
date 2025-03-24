module.exports = {
    testEnvironment: 'jsdom',
    setupFiles: [
        '<rootDir>/jest.setup.js'
    ],
    moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/static/js/$1',
        '^@src/(.*)$': '<rootDir>/static/js/src/$1'
    },
    moduleDirectories: [
        'node_modules',
        '<rootDir>/static/js/src'
    ],
    testMatch: [
        '**/static/js/tests/**/*.test.js',
        '**/static/js/src/**/*.test.js'
    ],
    transform: {
        '^.+\\.js$': 'babel-jest'
    },
    rootDir: '.'
}; 