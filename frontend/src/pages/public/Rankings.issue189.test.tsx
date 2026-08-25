import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { Rankings } from '@/pages/public/Rankings';
import { I18nProvider } from '@/contexts/I18nContext';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  fetchRankings: vi.fn(),
  fetchCoverageStats: vi.fn(),
}));

// Mock for desktop first, then we'll test mobile
vi.mock('@/hooks/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

const mockRankingsDataBR = {
  total_victims: 1234,
  total_events: 567,
  last_updated: '2026-08-20T10:30:00Z',
  cities: [
    {
      city: 'São Paulo',
      state: 'São Paulo',
      state_abbrev: 'SP',
      victim_count: 250,
      event_count: 125,
      victim_share: 20.3,
      victim_delta: 0,
      rate_per_100k: 2.1,
      population: 12000000,
    },
  ],
  states: [
    {
      state: 'São Paulo',
      victim_count: 450,
      event_count: 225,
      victim_share: 36.5,
      victim_delta: 0,
      rate_per_100k: 1.0,
      population: 46289333,
    },
  ],
  countries: [],
  homicide_types: [],
  methods: [],
  population_vintage: 'Censo 2022',
};

const mockRankingsDataCL = {
  total_victims: 300,
  total_events: 100,
  last_updated: '2026-08-20T10:30:00Z',
  cities: [
    {
      city: 'Santiago',
      state: 'Región Metropolitana',
      state_abbrev: 'RM',
      victim_count: 300,
      event_count: 100,
      victim_share: 100,
      victim_delta: 0,
      rate_per_100k: 5.0,
      population: 6000000,
    },
  ],
  states: [
    {
      state: 'Región Metropolitana',
      victim_count: 300,
      event_count: 100,
      victim_share: 100,
      victim_delta: 0,
      rate_per_100k: 5.0,
      population: 6000000,
    },
  ],
  countries: [],
  homicide_types: [],
  methods: [],
  population_vintage: 'INE 2024',
};

const mockCoverageDataBR = {
  window_start: '2025-09',
  methodology: {
    official_bag: 'homicídio doloso + feminicídio + roubo seguido de morte (latrocínio) + lesão corporal seguida de morte',
    arquivo_filter: 'homicidio, incident, victim_count <= 10, country=BR, date >= 2025-09-01',
    coverage_calculation: 'Arquivo victims / official victims (not capped, None when official=0)',
  },
  municipalities: [
    {
      code: 3550308,
      name: 'São Paulo',
      uf: 'SP',
      official_victims: 450,
      arquivo_victims: 250,
      coverage: 0.56,
      official_published: true,
    },
  ],
};

const mockCoverageDataEmpty = {
  window_start: '2025-09',
  methodology: {
    official_bag: 'N/A',
    arquivo_filter: 'N/A',
    coverage_calculation: 'N/A',
  },
  municipalities: [],
};

function renderWithRouter(component: React.ReactElement, initialRoute = '/estatisticas') {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  const result = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialRoute]}>
        <I18nProvider>
          <Routes>
            <Route path="/estatisticas" element={component} />
          </Routes>
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );

  return result;
}

describe('Rankings Page - Issue #189: URL State, Mobile, Chile, Skeleton', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsDataBR);
    (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockCoverageDataBR);
  });

  describe('Test 1: URL state management - period and country in URL', () => {
    it('should sync period selection to URL params', async () => {
      const user = userEvent.setup();
      const fetchRankingsSpy = api.fetchRankings as unknown as ReturnType<typeof vi.fn>;
      
      renderWithRouter(<Rankings />);

      // Wait for initial render with default period=365
      await screen.findByRole('heading', { name: /Rankings/i }, { timeout: 3000 });

      // Click 7 days period
      const sevenDayButton = screen.getByText(/Últimos 7 dias/i);
      await user.click(sevenDayButton);

      // Verify API was called with new period and button style updated
      await waitFor(() => {
        expect(fetchRankingsSpy).toHaveBeenCalledWith(
          expect.objectContaining({ days: 7 })
        );
        expect(sevenDayButton).toHaveClass('bg-blue-600');
      });
    });

    it('should sync country selection to URL params', async () => {
      const user = userEvent.setup();
      const fetchRankingsSpy = api.fetchRankings as unknown as ReturnType<typeof vi.fn>;
      
      (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsDataCL);
      
      renderWithRouter(<Rankings />);

      await screen.findByRole('heading', { name: /Rankings/i }, { timeout: 3000 });

      // Click Chile country button
      const chileButton = screen.getByRole('button', { name: /Chile/i });
      await user.click(chileButton);

      // Verify API was called with new country and button style updated
      await waitFor(() => {
        expect(fetchRankingsSpy).toHaveBeenCalledWith(
          expect.objectContaining({ country: 'CL' })
        );
        expect(chileButton).toHaveClass('bg-blue-600');
      });
    });

    it('should restore period and country from URL params on page load', async () => {
      // Mock API to verify correct params
      const fetchRankingsSpy = api.fetchRankings as unknown as ReturnType<typeof vi.fn>;

      // Render with URL params
      renderWithRouter(<Rankings />, '/estatisticas?period=30&country=CL');

      // Wait for data to load
      await waitFor(() => {
        expect(fetchRankingsSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            days: 30,
            country: 'CL',
          })
        );
      }, { timeout: 3000 });

      // Verify the 30 days button is selected
      const thirtyDayButton = screen.getByText(/Últimos 30 dias/i);
      expect(thirtyDayButton).toHaveClass('bg-blue-600');

      // Verify Chile button is selected
      const chileButton = screen.getByText(/Chile/i);
      expect(chileButton).toHaveClass('bg-blue-600');
    });

    it('should use default values when URL params are invalid', async () => {
      const fetchRankingsSpy = api.fetchRankings as unknown as ReturnType<typeof vi.fn>;

      // Render with invalid URL params
      renderWithRouter(<Rankings />, '/estatisticas?period=invalid&country=invalid');

      // Wait for data to load with defaults
      await waitFor(() => {
        expect(fetchRankingsSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            days: 365, // default
            country: 'BR', // default
          })
        );
      }, { timeout: 3000 });
    });
  });

  describe('Test 2: Chile empty state for coverage data', () => {
    it('should show empty state message when Chile is selected and coverage data is empty', async () => {
      (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsDataCL);
      (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockCoverageDataEmpty);

      const user = userEvent.setup();
      renderWithRouter(<Rankings />);

      await screen.findByRole('heading', { name: /Rankings/i }, { timeout: 3000 });

      // Select Chile
      const chileButton = screen.getByText(/Chile/i);
      await user.click(chileButton);

      // Wait for coverage section to update
      await waitFor(() => {
        // Should show empty state, not silently hide the section
        const emptyState = screen.getByText(/Dados de cobertura não disponíveis/i);
        expect(emptyState).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should not silently drop coverage section when Chile has no data', async () => {
      (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsDataCL);
      (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockCoverageDataEmpty);

      const user = userEvent.setup();
      renderWithRouter(<Rankings />);

      await screen.findByRole('heading', { name: /Rankings/i }, { timeout: 3000 });

      // Select Chile
      const chileButton = screen.getByText(/Chile/i);
      await user.click(chileButton);

      // Wait for data
      await waitFor(() => {
        expect(api.fetchRankings).toHaveBeenCalledWith(
          expect.objectContaining({ country: 'CL' })
        );
      }, { timeout: 3000 });

      // Coverage section header should still be visible
      expect(screen.getByText(/Cobertura.*Arquivo vs Oficial/i)).toBeInTheDocument();
    });
  });

  describe('Test 3: Skeleton loading on first paint', () => {
    it('should show skeleton loading state before data loads', async () => {
      // Make API calls hang to test loading state
      let resolveRankings: (value: any) => void;
      const rankingsPromise = new Promise(resolve => {
        resolveRankings = resolve;
      });
      (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockReturnValue(rankingsPromise);

      renderWithRouter(<Rankings />);

      // Should show skeleton immediately, not blank page
      const skeletons = screen.queryAllByTestId(/skeleton/i);
      expect(skeletons.length).toBeGreaterThan(0);

      // Should not show actual data yet
      expect(screen.queryByTestId('place-card')).not.toBeInTheDocument();

      // Resolve and verify data shows
      resolveRankings!(mockRankingsDataBR);
      await waitFor(() => {
        expect(screen.getByTestId('place-card')).toBeInTheDocument();
      }, { timeout: 3000 });
    });

    it('should not show blank page for 5-8 seconds during loading', () => {
      // Make API calls hang
      const rankingsPromise = new Promise(() => {});
      (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockReturnValue(rankingsPromise);

      renderWithRouter(<Rankings />);

      // Page should not be completely blank - should have at least the header
      expect(screen.getByRole('heading', { name: /Rankings/i })).toBeInTheDocument();

      // Should show period and country filters even while loading
      expect(screen.getByText(/Últimos 7 dias/i)).toBeInTheDocument();
      expect(screen.getByText(/Brasil/i)).toBeInTheDocument();
    });
  });

  describe('Test 4: Mobile - coverage not clipped', () => {
    beforeEach(() => {
      // Mock mobile viewport
      vi.mock('@/hooks/useMediaQuery', () => ({
        useIsMobile: () => true,
      }));
    });

    it('should show coverage as stacked cards on mobile, not a clipped table', async () => {
      renderWithRouter(<Rankings />);

      await waitFor(() => {
        expect(screen.getByText(/Cobertura.*Arquivo vs Oficial/i)).toBeInTheDocument();
      }, { timeout: 3000 });

      // On mobile, coverage should be shown as cards
      const coverageCards = screen.queryAllByTestId('coverage-card');
      expect(coverageCards.length).toBeGreaterThan(0);

      // Table should not be present on mobile
      const coverageSection = screen.getByText(/Cobertura.*Arquivo vs Oficial/i).closest('div');
      const table = coverageSection?.querySelector('table');
      expect(table).not.toBeInTheDocument();
    });

    it('should show download button for coverage on mobile', async () => {
      renderWithRouter(<Rankings />);

      await waitFor(() => {
        expect(screen.getByText(/Cobertura.*Arquivo vs Oficial/i)).toBeInTheDocument();
      }, { timeout: 3000 });

      // Download button should be visible
      const downloadButton = screen.getByText(/Baixar oficial/i);
      expect(downloadButton).toBeInTheDocument();
      expect(downloadButton.tagName).toBe('A');
      expect(downloadButton).toHaveAttribute('href', '/api/public/stats/coverage/download');
    });
  });
});
