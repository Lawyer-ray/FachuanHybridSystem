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
      // 依赖数组必须完整：基线为 0 违规，直接上 error 当门禁
      'react-hooks/exhaustive-deps': 'error',
      // 嵌套块深度：实证 max=4 在现有代码上 0 违规（整个仓库干净），基线为绿，
      // 因此直接上 error 当门禁（pnpm lint 带 --max-warnings 0，warn 等于直接挂红）。
      // 降到 3 会冒出 13 条存量告警、要额外做 ratchet，那是重构债不是门禁目标，故取 4。
      // 注意它数的是代码嵌套块（if/for/while 等），与目录层级无关。
      'max-depth': ['error', 4],
    },
  },
  // ===== 文件规模红线（见 docs/harness/frontend/index.md「文件规模红线」） =====
  // 这里只机器强制 >450 行硬红线（error）。为什么没有 350 行那一档：
  // eslint flat config 里同一规则被后出现的 block 匹配时，后块会【整体替换】
  // 前面的 severity+options，而不是两者并存。实测 eslint 10.11：
  //   先 warn@350 再 error@450 → 生效 [2, {max:450}]（后块赢）
  //   先 error@450 再 warn@350 → 生效 [1, {max:350}]（后块赢，硬红线失效）
  // 所以一个文件不可能同时拿到两档阈值；写两档只会留一条永不触发的死规则，
  // 比没有更误导人。结论：350 软红线保留为 review 期的人工判据（docs 已写明），
  // 机器只守 450。另：pnpm lint 跑的是 `eslint . --max-warnings 0`，
  // 意味着这里若配 warn 会直接把门禁挂红，这也是只留 error 的原因之一。
  // 单文件 ≤200 理想 / 200–350 可接受 / >350 拆分的分级判断仍按 docs 人工执行。
  {
    files: ['src/**/*.{ts,tsx}'],
    ignores: [
      '**/*.test.*',
      '**/__tests__/**',
      '**/*.d.ts',
      // 2026-11-11：文件规模技术债已全部清账，ratchet 白名单归零，
      // 硬红线对全仓库无条件生效（禁止再往这里加条目——超限就拆，不能豁免）。
      // 原 7 条的去向：
      //   demo-data.ts(2259) → components/demo-data/（15 模块，最大 357）
      //   demo-nonlit.ts(1583) → deal-detail/demo-nonlit/（9 模块，最大 422）
      //   material-prep/api.ts(588) → material-prep/api/（10 模块，最大 244）
      //   nonlit-workbench.tsx(532) → 50 行分派器 + 3 个页面组件
      //   GapPanel.tsx(699) → stages/gap/（8 模块，最大 132），主件 179 行
      //   DeskPage.tsx(468) → 269 行 + 两个 use-desk-* hook
      //   ReturnedPanel.tsx(805) → stages/returned/（10 模块，最大 189），主件 152 行
    ],
    rules: {
      'max-lines': ['error', { max: 450, skipBlankLines: false, skipComments: false }],
    },
  },
  // ===== 跨 feature 边界（见 docs/harness/frontend/index.md「归属与提权硬规则」） =====
  // 禁止 A feature 直接引 B feature 的内部文件，跨域只能走 `@/features/<name>` 桶出口，
  // 或者把公共部分提到 components/shared、lib、hooks。
  // `@/features/*/*` 只匹配「两段以上」的子路径，`@/features/<name>` 本身不受影响。
  {
    files: ['src/features/**/*.{ts,tsx}', 'src/components/**/*.{ts,tsx}', 'src/app/**/*.{ts,tsx}'],
    ignores: ['**/*.test.*', '**/__tests__/**', '**/*.d.ts'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              // copilot/launch 是唯一被架构决策放行的深路径（全局拉起 copilot 的公共事件口），
              // 用 patterns 的取反语法 `!` 豁免，避免为它开第二个 block。
              group: ['@/features/*/*', '!@/features/copilot/launch'],
              message:
                '跨 feature 禁止直接 import 其他 feature 的内部文件，请走该 feature 的桶出口 `@/features/<name>`（在其 index.ts re-export）；若两块都要用，应上提到 components/shared 或 lib。',
            },
          ],
        },
      ],
    },
  },
  // TODO(技术债)：以下 3 处存量跨域深引用暂时豁免，同上为 ratchet 而非默许。
  // 修法：把被引用的组件/函数提到 components/shared（或让目标 feature 在 index.ts 导出），
  // 然后删除对应条目。禁止往这里加新文件。
  {
    files: [
      'src/components/shared/AppNavbar.tsx', // -> @/features/workbench/components/NewProjectDialog
      'src/features/workbench/components/deal-detail/nonlit/special/special-bits.tsx', // -> @/features/bank-litigation/components/stages/DetailDrawer
      'src/features/workbench/components/deal-detail/PaymentPasteZone.tsx', // -> @/features/home/components/clipboard-file
    ],
    rules: {
      'no-restricted-imports': 'off',
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
