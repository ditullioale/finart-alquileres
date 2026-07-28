import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Compila los componentes React a la carpeta static de Flask.
// El bundle resultante (bundle.js / bundle.css) se sirve desde /static/js/react/.
// La ruta de salida se puede sobrescribir con BUILD_OUT (se usa al compilar en la nube).
export default defineConfig({
  plugins: [react()],
  base: '/static/js/react/',
  build: {
    outDir: process.env.BUILD_OUT || 'dist',
    emptyOutDir: true,
    manifest: false,
    rollupOptions: {
      output: {
        entryFileNames: 'bundle.js',
        assetFileNames: 'bundle.[ext]',
        chunkFileNames: 'chunk-[name].js',
      },
    },
  },
})
