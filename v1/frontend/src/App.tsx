import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Layout } from '@/components/Layout';
import { Dashboard } from '@/pages/Dashboard';
import { Sources } from '@/pages/Sources';
import { RawEvents } from '@/pages/RawEvents';
import { UniqueEvents } from '@/pages/UniqueEvents';
import { Jobs } from '@/pages/Jobs';

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
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/sources" element={<Sources />} />
            <Route path="/raw-events" element={<RawEvents />} />
            <Route path="/unique-events" element={<UniqueEvents />} />
            <Route path="/jobs" element={<Jobs />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

export default App;
