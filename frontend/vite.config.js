import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { writeFileSync, mkdirSync } from 'node:fs'
import { resolve } from 'node:path'

const buildId = `${Date.now()}`

const VENDOR_CHUNKS = {
  'vendor-react': ['react', 'react-dom', 'react-router', 'react-router-dom'],
  'vendor-flow': ['reactflow', '@reactflow/background', '@reactflow/controls'],
  'vendor-ui': ['antd', '@ant-design', 'lucide-react'],
  'vendor-utils': ['axios', 'zustand'],
  'vendor-mammoth': ['mammoth'],
  'vendor-virtual': ['@tanstack/react-virtual'],
}

function manualChunks(id) {
  if (!id.includes('node_modules')) return undefined
  for (const [chunkName, packages] of Object.entries(VENDOR_CHUNKS)) {
    for (const pkg of packages) {
      if (id.includes(`/node_modules/${pkg}/`) || id.includes(`/node_modules/${pkg}\\`)) {
        return chunkName
      }
    }
  }
  return undefined
}

function versionJsonPlugin() {
  return {
    name: 'emit-version-json',
    closeBundle() {
      const outDir = resolve(__dirname, 'dist')
      mkdirSync(outDir, { recursive: true })
      writeFileSync(
        resolve(outDir, 'version.json'),
        JSON.stringify(
          { buildId, builtAt: new Date().toISOString() },
          null,
          2,
        ),
        'utf-8',
      )
    },
  }
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), versionJsonPlugin()],
  define: {
    'import.meta.env.VITE_APP_BUILD_ID': JSON.stringify(buildId),
  },
  server: {
    port: 8173,
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:7788',
        changeOrigin: true,
      },
      '/health': {
        target: 'http://127.0.0.1:7788',
        changeOrigin: true,
      },
      '/ws': {
        target: 'http://127.0.0.1:7788',
        ws: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks,
      },
    },
    chunkSizeWarningLimit: 600,
  },
})
