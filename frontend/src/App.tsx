import { lazy, Suspense, useEffect, type ComponentProps } from 'react';
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { I18nProvider } from '@/contexts/I18nContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { AdminLayout } from '@/components/AdminLayout';
import { initGA, trackPageView } from '@/lib/analytics';
import { Loader2 } from 'lucide-react';

// Map portal — code-split so deck.gl / maplibre (~2.5 MB) load only on public routes
const MapExplorer = lazy(() =>
  import('@/pages/public/MapExplorer').then((m) => ({ default: m.MapExplorer }))
);

// Admin pages
import { Login } from '@/pages/admin/Login';
import { Dashboard } from '@/pages/admin/Dashboard';
import { Sources } from '@/pages/admin/Sources';
import { RawEvents } from '@/pages/admin/RawEvents';
import { RawEventDetail } from '@/pages/admin/RawEventDetail';
import { UniqueEvents } from '@/pages/admin/UniqueEvents';
import { Jobs } from '@/pages/admin/Jobs';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5000,
      retry: 1,
    },
  },
});

function PortalFallback() {
  return (
    <div
      className="fixed inset-0 flex items-center justify-center"
      style={{ background: 'var(--stone-100)', color: 'var(--color-text-muted)' }}
    >
      <Loader2 className="h-8 w-8 animate-spin" style={{ color: 'var(--blue-500)' }} />
    </div>
  );
}

function MapExplorerRoute(props: ComponentProps<typeof MapExplorer>) {
  return (
    <Suspense fallback={<PortalFallback />}>
      <MapExplorer {...props} />
    </Suspense>
  );
}

function RouteTracker() {
  const location = useLocation();

  useEffect(() => {
    initGA();
    trackPageView(location.pathname + location.search, document.title);
  }, [location]);

  return null;
}

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <I18nProvider>
        <AuthProvider>
          <BrowserRouter>
            <RouteTracker />
            <Routes>
              <Route path="/" element={<MapExplorerRoute initialMode="stats" />} />
              <Route path="/eventos" element={<MapExplorerRoute initialMode="feed" />} />
              <Route path="/eventos/:id" element={<MapExplorerRoute initialMode="feed" />} />
              <Route path="/dados" element={<MapExplorerRoute initialMode="data" />} />
              <Route path="/sobre" element={<MapExplorerRoute initialMode="stats" initialAbout />} />

              <Route path="/admin/login" element={<Login />} />

              <Route path="/admin" element={<ProtectedRoute><AdminLayout><Dashboard /></AdminLayout></ProtectedRoute>} />
              <Route path="/admin/sources" element={<ProtectedRoute><AdminLayout><Sources /></AdminLayout></ProtectedRoute>} />
              <Route path="/admin/raw-events" element={<ProtectedRoute><AdminLayout><RawEvents /></AdminLayout></ProtectedRoute>} />
              <Route path="/admin/raw-events/:id" element={<ProtectedRoute><AdminLayout><RawEventDetail /></AdminLayout></ProtectedRoute>} />
              <Route path="/admin/unique-events" element={<ProtectedRoute><AdminLayout><UniqueEvents /></AdminLayout></ProtectedRoute>} />
              <Route path="/admin/jobs" element={<ProtectedRoute><AdminLayout><Jobs /></AdminLayout></ProtectedRoute>} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </I18nProvider>
    </QueryClientProvider>
  );
}

export default App;
