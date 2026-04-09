import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
    setupFiles: ['./src/test-setup.ts'],
    include: ['src/**/*.test.{ts,tsx}'],
  },
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    open: true,
    strictPort: false,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          // React 核心
          'vendor-react': ['react', 'react-dom', 'react-router'],
          // 动画库（较重，单独拆出）
          'vendor-motion': ['framer-motion'],
          // 数据层
          'vendor-query': ['@tanstack/react-query'],
          // 表单
          'vendor-form': ['react-hook-form', '@hookform/resolvers', 'zod'],
          // UI 基础组件（Radix）
          'vendor-radix': [
            '@radix-ui/react-dialog',
            '@radix-ui/react-select',
            '@radix-ui/react-tabs',
            '@radix-ui/react-alert-dialog',
            '@radix-ui/react-dropdown-menu',
            '@radix-ui/react-tooltip',
            '@radix-ui/react-label',
            '@radix-ui/react-separator',
            '@radix-ui/react-avatar',
            '@radix-ui/react-progress',
            '@radix-ui/react-slot',
          ],
          // HTTP + 工具
          'vendor-utils': ['ky', 'date-fns', 'clsx', 'tailwind-merge', 'class-variance-authority', 'sonner'],
          // 状态管理
          'vendor-state': ['zustand'],
        },
      },
    },
  },
})
