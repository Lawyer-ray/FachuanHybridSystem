import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    globals: true,
    // 双环境策略：默认 node（纯逻辑单测，速度快、无 DOM 噪音）；
    // 需要 DOM 的 hooks/组件测试在文件头加 docblock `// @vitest-environment jsdom`
    // 单文件切到 jsdom（命名约定 **/*.dom.test.tsx），对既有 node 用例零影响。
    // 注：vitest 3 起 environmentMatchGlobs 已移除，per-file docblock 是官方推荐做法。
    environment: 'node',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{ts,tsx}'],
      reporter: ['text', 'json-summary', 'json'],
      reportsDirectory: 'coverage',
      exclude: [
        'src/components/ui/**',
        'src/**/*.test.{ts,tsx}',
        'src/**/*.d.ts',
        'src/main.tsx',
        'src/vite-env.d.ts',
        'src/types/api-schema.demo.ts',
      ],
      // 棘轮（2026-10-05 补测批实测 lines 49.7%，阈值留抖动余量）：只升不降，
      // 新增未测试的组件/页面会拉低全量数字并被拦下——升级方式为
      // 补测后同步抬高此处数字
      thresholds: { lines: 47, functions: 43, statements: 46, branches: 36 },
    },
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5090,
    open: true,
    strictPort: false,
    // Cloudflare Tunnel 外网访问经 app.xlaw.top 进来，Vite 8 默认拒绝非
    // localhost 的 Host 头（DNS rebinding 防护），显式放行隧道域名。
    allowedHosts: ["app.xlaw.top"],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      // 后端 media（文书识别预览等）：相对链接 /media/... 由前端渲染（iframe/img），
      // 不代理会打到 Vite SPA 兜底路由被重定向回首页
      '/media': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
      // 社交登录：授权页/回调走 Django View，需与后端同源才能带 session cookie
      // （state 存 session，跨域下 SameSite=Lax 不发送，回调会报 invalid_session）
      //
      // 必须带尾斜杠（匹配 /social/feishu/callback/ 这类后端路径）：Vite 的字符串
      // key 是**前缀匹配**，写成 '/social' 会把前端路由 /social-callback 也转发给
      // Django，导致回调页 404。
      '^/social/': {
        target: 'http://127.0.0.1:8002',
        changeOrigin: true,
      },
    },
  },
  build: {
    target: "es2022",
    reportCompressedSize: false,
    // 生产 sourcemap 用 hidden：生成 .map 便于本地按图对回源码排障，
    // 但产物 JS 不带 //# sourceMappingURL 引用——公网拿不到 map，防止
    // 前台站点被还原源码（app.xlaw.top 隧道暴露场景）。
    sourcemap: 'hidden',
    // material-prep 懒加载 chunk 含 pdfjs（~520KB）属预期：只在进入该路由时才下载。
    // 阈值放宽到 600，避免这条已知大 chunk 的告警长期刷屏、掩盖新出现的问题。
    chunkSizeWarningLimit: 600,
    rollupOptions: {
      output: {
        // 只列实际安装的包（此前残留 10 个未安装包的死规则，读配置时误导）
        manualChunks(id: string) {
          // Vite 虚拟模块（\0vite/preload-helper.js 等）不走 node_modules 分支，
          // 默认分桶曾把它塞进 vendor-pdf，形成「入口 → helper → pdfjs」静态边，
          // 路由懒加载失效。归入首屏必加载的 vendor-react，不给关键路径添新依赖。
          if (id.startsWith('\0vite/')) return 'vendor-react'
          // 取最后一个 node_modules/ 之后的真实包路径段。注意不能用
          // id.includes(pkg) 宽匹配：'lucide-react'、'@radix-ui/react-*'、
          // '@tanstack/react-query' 的路径全都含 "react"，曾把图标库、UI 库、
          // 状态库整个吸进 vendor-react（首屏背上懒加载页的图标 + 缓存失效放大）。
          const idx = id.lastIndexOf('node_modules/')
          if (idx < 0) return
          const rest = id.slice(idx + 'node_modules/'.length)
          const belongs = (pkgs: string[]) => pkgs.some((p) => rest === p || rest.startsWith(`${p}/`))
          const chunks: Array<[string, string[]]> = [
            ['vendor-react', ['react', 'react-dom', 'react-router', 'scheduler']],
            ['vendor-query', ['@tanstack/react-query', '@tanstack/query-core']],
            ['vendor-radix', ['@radix-ui', 'react-remove-scroll', 'react-remove-scroll-bar', 'react-style-singleton', 'use-callback-ref']],
            ['vendor-utils', ['ky', 'date-fns', 'clsx', 'tailwind-merge', 'class-variance-authority', 'sonner']],
            ['vendor-state', ['zustand']],
            ['vendor-icons', ['lucide-react']],
          ]
          for (const [chunk, pkgs] of chunks) {
            if (belongs(pkgs)) return chunk
          }
        },
      },
    },
  },
})
