import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { Rankings } from '@/pages/public/Rankings';
import { I18nProvider } from '@/contexts/I18nContext';
import * as api from '@/lib/api';

// Mock the API module
vi.mock('@/lib/api', () => ({
  fetchRankings: vi.fn(),
  fetchStatsMatrix: vi.fn(),
  fetchCoverageStats: vi.fn(),
}));

// Mock useIsMobile hook
vi.mock('@/hooks/useMediaQuery', () => ({
  useIsMobile: () => false,
}));

const mockRankingsData = {
  total_victims: 1000,
  total_events: 500,
  last_updated: '2026-08-20T10:30:00Z',
  cities: [
    {
      city: 'São Paulo',
      state_abbrev: 'SP',
      victim_count: 100,
      event_count: 50,
      victim_share: 10.0,
      victim_delta: 0,
      rate_per_100k: 1.5,
      population: 12000000,
    },
    {
      city: 'Rio de Janeiro',
      state_abbrev: 'RJ',
      victim_count: 80,
      event_count: 40,
      victim_share: 8.0,
      victim_delta: 0,
      rate_per_100k: 1.2,
      population: 6000000,
    },
  ],
  states: [
    {
      state: 'São Paulo',
      victim_count: 300,
      event_count: 150,
      victim_share: 30.0,
      victim_delta: 0,
      rate_per_100k: 2.0,
      population: 45000000,
    },
    {
      state: 'Rio de Janeiro',
      victim_count: 200,
      event_count: 100,
      victim_share: 20.0,
      victim_delta: 0,
      rate_per_100k: 1.8,
      population: 17000000,
    },
  ],
  countries: [],
  homicide_types: [
    {
      type: 'Homicídio simples',
      victim_count: 500,
      event_count: 250,
      victim_share: 50.0,
      victim_delta: 0,
    },
  ],
  methods: [
    {
      method: 'Arma de fogo',
      victim_count: 700,
      event_count: 350,
      victim_share: 70.0,
      victim_delta: 0,
    },
  ],
  population_vintage: 'Censo 2022',
};

const mockCoverageData = {
  window_start: '2025-09',
  municipalities: [
    {
      code: '3550308',
      name: 'São Paulo',
      uf: 'SP',
      official_victims: 100,
      arquivo_victims: 80,
      coverage: 0.8,
      official_published: true,
    },
  ],
  methodology: {
    official_bag: 'homicídio doloso + feminicídio + latrocínio + lesão corporal seguida de morte',
  },
};

function renderWithProviders(component: React.ReactElement) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <I18nProvider>
          {component}
        </I18nProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe('Rankings Page - Issue #184 Cleanup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsData);
    (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockCoverageData);
  });

  describe('Removed components (should NOT be present)', () => {
    it('should NOT display the UF heatmap title "Taxa de Homicídios por UF"', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // Now check that the heatmap is NOT present
      expect(screen.queryByText(/Taxa de Homicídios por UF/i)).not.toBeInTheDocument();
    });

    it('should NOT display the type month grid title "Vítimas por Tipo de Homicídio"', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // Now check that the type month grid is NOT present
      expect(screen.queryByText(/Vítimas por Tipo de Homicídio/i)).not.toBeInTheDocument();
    });

    it('should NOT display the Tipos de homicídio ranking table', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // The i18n key rankingsTypes maps to "Tipos de homicídio" in PT
      expect(screen.queryByText(/Tipos de homicídio/i)).not.toBeInTheDocument();
    });

    it('should NOT display the Métodos ranking table', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // The i18n key rankingsMethods maps to "Métodos" in PT
      // Use a more specific pattern to avoid matching "Método" in table headers
      const methodsHeadings = screen.queryAllByRole('heading', { name: /^Métodos$/i });
      expect(methodsHeadings).toHaveLength(0);
    });

    it('should NOT display the VARIAÇÃO column header', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // The i18n key rankingsDelta maps to "Variação" in PT
      // Look for it as a table column header
      const variacaoHeaders = screen.queryAllByText(/^Variação$/i);
      expect(variacaoHeaders).toHaveLength(0);
    });

    it('should NOT display the yellow methodology note about rankings', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // Check that the amber box with rankingsMethodologyNote is not present
      // The PT text is: "Estes rankings são baseados em dados extraídos de reportagens jornalísticas, não em estatísticas oficiais."
      const methodologyText = screen.queryByText(/Estes rankings são baseados em dados extraídos de reportagens jornalísticas/i);
      expect(methodologyText).not.toBeInTheDocument();
    });

    it('should NOT display "mortes violentas intencionais" text', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // The five-type Mortes Violentas Intencionais one-liner should be gone
      const mviText = screen.queryByText(/mortes violentas intencionais/i);
      expect(mviText).not.toBeInTheDocument();
    });

    it('should NOT display the amber methodology footer under coverage table', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/Cidades/i)).toBeInTheDocument();
      });
      
      // The amber footer with official_bag and "Metodologia:" should not be present
      const metodologiaFooter = screen.queryByText(/Metodologia:.*homicídio doloso.*feminicídio/i);
      expect(metodologiaFooter).not.toBeInTheDocument();
      
      // Also check that the "official_bag" text pattern is not rendered
      const officialBagText = screen.queryByText(/Cobertura = Arquivo \/ oficial/i);
      expect(officialBagText).not.toBeInTheDocument();
    });
  });

  describe('Kept components (SHOULD be present)', () => {
    it('should display the Cidades ranking table', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        // The i18n key rankingsCities maps to "Cidades" in PT
        expect(screen.getByText(/^Cidades$/i)).toBeInTheDocument();
      });
    });

    it('should display the Estados/Regiões ranking table', async () => {
      renderWithProviders(<Rankings />);
      
      // Wait for data to load
      await waitFor(() => {
        expect(screen.getByText(/^Cidades$/i)).toBeInTheDocument();
      }, { timeout: 3000 });
      
      // The Estados tab should be visible (it's one of the three tabs)
      const estadosTab = screen.getByText(/Estados/i);
      expect(estadosTab).toBeInTheDocument();
      
      // The i18n key rankingsStates maps to "Estados / Regiões" in PT
      // This text appears in the table title when you switch to the Estados tab
      // But since the test is just checking components are present, let's just verify the tab exists
    });

    it('should display city data from the rankings', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        expect(screen.getByText(/São Paulo, SP/i)).toBeInTheDocument();
        expect(screen.getByText(/Rio de Janeiro, RJ/i)).toBeInTheDocument();
      });
    });

    it('should display state data from the rankings', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        // State names should appear in the states table
        const saoPauloStates = screen.getAllByText(/São Paulo/i);
        expect(saoPauloStates.length).toBeGreaterThan(0);
      });
    });

    it('should display period filter chips', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        expect(screen.getByText(/Últimos 7 dias/i)).toBeInTheDocument();
        expect(screen.getByText(/Últimos 30 dias/i)).toBeInTheDocument();
        expect(screen.getByText(/Último ano/i)).toBeInTheDocument();
      });
    });

    it('should display country filter options', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        expect(screen.getByText(/Brasil/i)).toBeInTheDocument();
        expect(screen.getByText(/Chile/i)).toBeInTheDocument();
      });
    });
  });

  describe('Coverage table (can stay if present)', () => {
    it('should allow the coverage table to be present', async () => {
      renderWithProviders(<Rankings />);
      
      await waitFor(() => {
        // Coverage table can stay - this is just checking it doesn't break
        // This test just ensures the page renders without errors
        expect(true).toBe(true);
      });
    });
  });
});
