import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react-swc"
import { defineConfig } from "vite"

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  // 新增服务器配置，允许局域网访问
  server: {
    // 监听所有网络接口（关键），让局域网设备能访问
    host: "0.0.0.0",
    // 可选：指定端口（默认是 5173，也可以改成你习惯的如 3000）
    port: 5173,
    // 可选：自动打开浏览器（不需要的话可以删掉）
    open: true,
    // 可选：禁用端口占用时的自动重试（根据需要调整）
    strictPort: false,
  },
})
