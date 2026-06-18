import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vitest/config"

export default defineConfig({
  test: {
    globals: true,
    environment: 'jsdom',
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
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    open: true,
    strictPort: false,
    proxy: {
      '/api': {
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
