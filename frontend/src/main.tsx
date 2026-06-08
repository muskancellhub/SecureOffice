import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { AppRouter } from './router/AppRouter';
import { AuthProvider } from './context/AuthContext';
import { ToastHost } from './components/ToastHost';
import './api/toastInterceptor';
import './styles/global.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
        <ToastHost />
      </AuthProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
