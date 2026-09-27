import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    globals: true,
    // 仓库当前未装 jsdom（此前无用例所以没暴露）。纯逻辑用例用 node 环境即可；
    // 需要 DOM 的组件测试请先 `pnpm add -D jsdom` 再改回 'jsdom'。
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
        'src/routes/index.tsx',  // lazy() imports cannot be covered in unit tests
      ],
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
    proxy: {
      '/api': {
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
    target: 'es2022',
    reportCompressedSize: false,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return
          const chunks: Record<string, string[]> = {
            'vendor-react': ['react', 'react-dom', 'react-router'],
            'vendor-motion': ['framer-motion'],
            'vendor-query': ['@tanstack/react-query'],
            'vendor-form': ['react-hook-form', '@hookform/resolvers', 'zod'],
            'vendor-radix': ['@radix-ui/'],
            'vendor-utils': ['ky', 'date-fns', 'clsx', 'tailwind-merge', 'class-variance-authority', 'sonner'],
            'vendor-state': ['zustand'],
            'vendor-recharts': ['recharts'],
            'vendor-markdown': ['react-markdown', 'rehype-highlight', 'remark-gfm', 'highlight.js'],
            'vendor-dnd': ['@dnd-kit/'],
          }
          for (const [chunk, pkgs] of Object.entries(chunks)) {
            if (pkgs.some((pkg) => id.includes(pkg))) return chunk
          }
        },
      },
    },
  },
})
