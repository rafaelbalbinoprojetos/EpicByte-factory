import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({plugins:[react()],build:{rollupOptions:{output:{manualChunks:{charts:['echarts/core','echarts/charts','echarts/components','echarts/renderers'],react:['react','react-dom']}}}},server:{host:'127.0.0.1'},test:{environment:'jsdom',globals:true}});
