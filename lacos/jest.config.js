module.exports = {
    testEnvironment: 'jsdom',
    setupFiles: ['./jest.setup.js'],
    moduleNameMapper: {
        '^@/(.*)$': '<rootDir>/lacos/$1'
    },
    testMatch: [
        '**/tests/**/*.js',
        '**/tests/**/*.jsx'
    ],
    transform: {
        '^.+\\.js$': 'babel-jest'
    }
}; 