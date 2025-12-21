import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { PublicLayout } from '@/components/PublicLayout';
import { AdminLayout } from '@/components/AdminLayout';

// Public pages
import { Home } from '@/pages/public/Home';
import { Events } from '@/pages/public/Events';
import { Data } from '@/pages/public/Data';
import { About } from '@/pages/public/About';

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

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            {/* Public routes */}
            <Route path="/" element={<PublicLayout><Home /></PublicLayout>} />
            <Route path="/eventos" element={<PublicLayout><Events /></PublicLayout>} />
            <Route path="/dados" element={<PublicLayout><Data /></PublicLayout>} />
            <Route path="/sobre" element={<PublicLayout><About /></PublicLayout>} />
            
            {/* Admin login */}
            <Route path="/admin/login" element={<Login />} />
            
            {/* Protected admin routes */}
            <Route path="/admin" element={<ProtectedRoute><AdminLayout><Dashboard /></AdminLayout></ProtectedRoute>} />
            <Route path="/admin/sources" element={<ProtectedRoute><AdminLayout><Sources /></AdminLayout></ProtectedRoute>} />
            <Route path="/admin/raw-events" element={<ProtectedRoute><AdminLayout><RawEvents /></AdminLayout></ProtectedRoute>} />
            <Route path="/admin/raw-events/:id" element={<ProtectedRoute><AdminLayout><RawEventDetail /></AdminLayout></ProtectedRoute>} />
            <Route path="/admin/unique-events" element={<ProtectedRoute><AdminLayout><UniqueEvents /></AdminLayout></ProtectedRoute>} />
            <Route path="/admin/jobs" element={<ProtectedRoute><AdminLayout><Jobs /></AdminLayout></ProtectedRoute>} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export default App;
