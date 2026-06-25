import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  root: '.',
  build: {
    outDir: 'popup',
    emptyOutDir: false, // keep original files for now or let it overwrite index.html etc
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
      },
      output: {
        entryFileNames: 'popup.js',
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith('.css')) {
            return 'popup.css';
          }
          return '[name].[ext]';
        },
        chunkFileNames: '[name].js',
      }
    }
  }
})
