import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import {App} from '@/App';
import './styles/index.css';

export {App};
export {progress, title} from '@/lib/format';

if (!import.meta.env.MODE.includes('test')) {
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
