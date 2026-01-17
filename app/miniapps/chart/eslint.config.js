import globals from 'globals';

export default [
    {
        files: ['js/**/*.js'],
        languageOptions: {
            ecmaVersion: 2022,
            sourceType: 'module',
            globals: {
                ...globals.browser,
                LightweightCharts: 'readonly',
                Telegram: 'readonly',
            },
        },
        rules: {
            'no-unused-vars': ['warn', { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
            'no-console': ['warn', { allow: ['warn', 'error'] }],
            'prefer-const': 'warn',
            'eqeqeq': ['error', 'always'],
            'curly': ['error', 'multi-line'],
            'no-var': 'error',
            'semi': ['error', 'always'],
            'quotes': ['warn', 'single', { avoidEscape: true }],
            'indent': ['warn', 4, { SwitchCase: 1 }],
            'comma-dangle': ['warn', 'always-multiline'],
            'arrow-parens': ['warn', 'as-needed'],
            'object-shorthand': 'warn',
        },
    },
];
