import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import {fileURLToPath, URL} from 'node:url';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {alias: {'@': fileURLToPath(new URL('./src', import.meta.url))}},
  // Caminhos relativos: o site abre em qualquer pasta/porta da pré-visualização.
  base: './',
  build: {assetsInlineLimit: 0},
  test: {environment: 'jsdom', globals: true, css: false, setupFiles: ['./src/test-setup.ts']},
});
