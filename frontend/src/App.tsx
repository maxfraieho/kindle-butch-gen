import React from 'react';
import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { Theme, vydraTheme } from './theme/vydraTheme';
import { AuthProvider, useAuth } from './context/AuthContext';
import { AppShell } from './components/layout/AppShell';
import { Login } from './pages/Login';
import { Dashboard } from './pages/Dashboard';
import { StagesView } from './pages/StagesView';
import { DownloadsView } from './pages/DownloadsView';
import { SettingsView } from './pages/SettingsView';
import { MangaEditor } from './pages/MangaEditor';
import { ModesView } from './pages/ModesView';

const ProtectedRoute: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { authenticated, loading } = useAuth();

  if (loading) {
    return (
      <div className="min-h-screen bg-[#090d16] flex items-center justify-center text-emerald-400">
        <div className="w-8 h-8 border-2 border-emerald-400 border-r-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!authenticated) {
    return <Navigate to="/login" replace />;
  }

  return <AppShell>{children}</AppShell>;
};

export const App: React.FC = () => {
  return (
    <Theme theme={vydraTheme} mode="dark">
      <AuthProvider>
        <Router>
          <Routes>
            <Route path="/login" element={<Login />} />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Dashboard />
                </ProtectedRoute>
              }
            />
            <Route
              path="/view/:slug"
              element={
                <ProtectedRoute>
                  <StagesView />
                </ProtectedRoute>
              }
            />
            <Route
              path="/manga/:slug"
              element={
                <ProtectedRoute>
                  <MangaEditor />
                </ProtectedRoute>
              }
            />
            <Route
              path="/downloads"
              element={
                <ProtectedRoute>
                  <DownloadsView />
                </ProtectedRoute>
              }
            />
            <Route
              path="/modes"
              element={
                <ProtectedRoute>
                  <ModesView />
                </ProtectedRoute>
              }
            />
            <Route
              path="/settings"
              element={
                <ProtectedRoute>
                  <SettingsView />
                </ProtectedRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
      </AuthProvider>
    </Theme>
  );
};

export default App;
