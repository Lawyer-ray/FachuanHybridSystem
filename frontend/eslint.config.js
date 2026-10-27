import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  // api-schema.d.ts 是 openapi-typescript 生成物（3 万+ 行），不参与 lint；
  // 再生成流程见 src/types/README.md
  // prototype/ 是原型草稿（含一次性 Playwright 脚本与讨论用 plugin.js），
  // 不是产线代码：里面有顶层 return 的脚本片段，按产线语法检查必然报
  // Parsing error。它也不该被 review/门禁拖住，因此整体排除。
  globalIgnores(['dist', 'src/types/api-schema.d.ts', 'prototype']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommendedTypeChecked,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.browser,
      parserOptions: { projectService: true },
    },
    rules: {
      // React Compiler 规则：setState in effect 是常见合法模式（表单重置、路由变化等）
      'react-hooks/set-state-in-effect': 'off',
      'react-hooks/immutability': 'off',
      // 允许 _ 前缀的未使用变量（解构排除模式）
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }],
    },
  },
  {
    files: ['**/__tests__/**', '**/*.test.*'],
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
      '@typescript-eslint/no-unused-vars': 'off',
      '@typescript-eslint/no-require-imports': 'off',
      '@typescript-eslint/no-unsafe-function-type': 'off',
      '@typescript-eslint/no-this-alias': 'off',
      'no-unused-vars': 'off',
      'no-constant-binary-expression': 'off',
      // 测试文件的 type-checked 降噪：mock（vi.fn() 返回 any）、fire-and-forget
      // 断言、无 await 的 async mock 实现都是测试惯用写法，不按产线口径检查。
      // 生产代码不在此豁免范围，仍走完整 recommendedTypeChecked。
      '@typescript-eslint/unbound-method': 'off',
      '@typescript-eslint/require-await': 'off',
      '@typescript-eslint/no-unnecessary-type-assertion': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
      '@typescript-eslint/no-unsafe-member-access': 'off',
      '@typescript-eslint/no-unsafe-call': 'off',
      '@typescript-eslint/no-unsafe-argument': 'off',
      '@typescript-eslint/no-unsafe-return': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
    },
  },
])
