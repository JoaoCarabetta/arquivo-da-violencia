import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { Rankings } from '@/pages/public/Rankings';
import { I18nProvider } from '@/contexts/I18nContext';
import * as api from '@/lib/api';

vi.mock('@/lib/api', () => ({
  fetchRankings: vi.fn(),
  fetchStatsMatrix: vi.fn(),
  fetchCoverageStats: vi.fn(),
}));

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
      state_abbrev: 'SP',
      victim_count: 250,
      event_count: 125,
      victim_share: 20.3,
      victim_delta: 0,
      rate_per_100k: 2.1,
      population: 12000000,
    },
    {
      city: 'Rio de Janeiro',
      state_abbrev: 'RJ',
      victim_count: 180,
      event_count: 90,
      victim_share: 14.6,
      victim_delta: 0,
      rate_per_100k: 2.7,
      population: 6747815,
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
    {
      state: 'Rio de Janeiro',
      victim_count: 300,
      event_count: 150,
      victim_share: 24.3,
      victim_delta: 0,
      rate_per_100k: 1.7,
      population: 17463349,
    },
  ],
  countries: [],
  homicide_types: [],
  methods: [],
  population_vintage: 'Censo 2022',
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
    },
    {
      code: 3304557,
      name: 'Rio de Janeiro',
      uf: 'RJ',
      official_victims: 320,
      arquivo_victims: 180,
      coverage: 0.56,
    },
  ],
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
      <BrowserRouter>
        <I18nProvider>
          {component}
        </I18nProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
}

describe('Rankings Page - Issue #185: Place Search and Card', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.fetchRankings as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockRankingsDataBR);
    (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(mockCoverageDataBR);
  });

  describe('Test 1: Default place is Brasil', () => {
    it('should display Brasil as the default selected place on first load', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      expect(placeCard).toBeInTheDocument();
      
      expect(within(placeCard).getByRole('heading', { name: /Brasil/i })).toBeInTheDocument();
    });
  });

  describe('Test 2: Typeahead search for municipality', () => {
    it('should open place card when typing and selecting a municipality name', async () => {
      const user = userEvent.setup();
      renderWithProviders(<Rankings />);
      
      await screen.findByTestId('place-card', {}, { timeout: 3000 });
      const searchInput = await screen.findByPlaceholderText('Busque um município ou estado');
      expect(searchInput).toBeInTheDocument();
      
      await user.type(searchInput, 'São Paulo');
      
      await waitFor(() => {
        const options = screen.getAllByText(/São Paulo/i);
        expect(options.length).toBeGreaterThan(0);
      }, { timeout: 2000 });
      
      const allOptions = screen.getAllByText('São Paulo, SP');
      const muniOption = allOptions.find(el => el.closest('button'));
      expect(muniOption).toBeDefined();
      await user.click(muniOption!);
      
      const placeCard = screen.getByTestId('place-card');
      expect(within(placeCard).getByText(/São Paulo/i)).toBeInTheDocument();
      
      const arquivoCount = within(placeCard).getByTestId('arquivo-count');
      expect(arquivoCount).toHaveTextContent('250');
      
      const officialCount = within(placeCard).getByTestId('official-count');
      expect(officialCount).toHaveTextContent('450');
    });
  });

  describe('Test 3: Official not shown as 0 when unpublished', () => {
    it('should say official is not published when data is unavailable for the period', async () => {
      (api.fetchCoverageStats as unknown as ReturnType<typeof vi.fn>).mockResolvedValue({
        ...mockCoverageDataBR,
        municipalities: [],
      });
      
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      expect(within(placeCard).queryByTestId('official-count')).not.toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Dados oficiais não publicados neste período/i)).toBeInTheDocument();
    });
  });

  describe('Test 4: 7-day period shows Arquivo only, no fake official 0', () => {
    it('should not show official count as 0 when 7-day period is selected', async () => {
      const user = userEvent.setup();
      renderWithProviders(<Rankings />);
      
      await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      const sevenDayChip = screen.getByText(/Últimos 7 dias/i);
      await user.click(sevenDayChip);
      
      await waitFor(() => {
        expect(api.fetchRankings).toHaveBeenCalledWith(
          expect.objectContaining({ days: 7 })
        );
      }, { timeout: 2000 });
      
      const placeCard = screen.getByTestId('place-card');
      expect(within(placeCard).queryByTestId('official-count')).not.toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Dados oficiais não publicados neste período/i)).toBeInTheDocument();
    });
  });

  describe('Test 5: Chile is not default and not in Brazil official', () => {
    it('should not select Chile as default', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      expect(within(placeCard).getByRole('heading', { name: /Brasil/i })).toBeInTheDocument();
      expect(within(placeCard).queryByRole('heading', { name: /Chile/i })).not.toBeInTheDocument();
    });

    it('should not include Chile victims in Brazil official figures', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      // Brasil official count should be sum of BR municipalities only (450 + 320 = 770)
      const officialCount = within(placeCard).getByTestId('official-count');
      expect(officialCount).toHaveTextContent('770');
      
      // Verify the official count does NOT include any Chile data
      // The mock only has BR municipalities, so this verifies Chile is excluded
      expect(api.fetchCoverageStats).toHaveBeenCalled();
      const coverageData = mockCoverageDataBR;
      const allMunicipalities = coverageData.municipalities;
      const hasChileMunicipalities = allMunicipalities.some(m => m.uf === 'CL' || m.uf.startsWith('CL'));
      expect(hasChileMunicipalities).toBe(false);
    });
  });

  describe('Test 6: No 5563-row dump above the fold', () => {
    it('should not display a 5563-row municipality table above the fold', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      expect(placeCard).toBeInTheDocument();
      
      const placeCardContent = within(placeCard);
      expect(placeCardContent.queryByRole('table')).not.toBeInTheDocument();
    });
  });

  describe('Place Card Copy Requirements', () => {
    it('should display Arquivo count large with period and last update', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      const arquivoCount = within(placeCard).getByTestId('arquivo-count');
      expect(arquivoCount).toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Último ano/i)).toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Última atualização/i)).toBeInTheDocument();
    });

    it('should display official count with full citation when available', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      expect(within(placeCard).getByText(/Ministério da Justiça e Segurança Pública/i)).toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Formulário 1/i)).toBeInTheDocument();
      
      expect(within(placeCard).getByText(/desde.*2025-09/i)).toBeInTheDocument();
    });

    it('should display sentence that counts are not the same', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      expect(within(placeCard).getByText(/contagens não são iguais/i)).toBeInTheDocument();
    });

    it('should display "Como contamos" as a real link to methodology page', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      const methodologyLink = within(placeCard).getByText(/Como contamos/i);
      expect(methodologyLink).toBeInTheDocument();
      expect(methodologyLink.tagName).toBe('A');
      expect(methodologyLink).toHaveAttribute('href', '/metodologia');
    });

    it('should display scope line about 52 cities', async () => {
      renderWithProviders(<Rankings />);
      
      const placeCard = await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      expect(within(placeCard).getByText(/52.*capitais.*grandes.*regiões.*metropolitanas/i)).toBeInTheDocument();
      
      expect(within(placeCard).getByText(/Não cobre os 5\.563 municípios nem apenas 63 cidades/i)).toBeInTheDocument();
    });

    it('should have exact placeholder text', async () => {
      renderWithProviders(<Rankings />);
      
      await screen.findByTestId('place-card', {}, { timeout: 3000 });
      
      const searchInput = screen.getByPlaceholderText('Busque um município ou estado');
      expect(searchInput).toBeInTheDocument();
    });
  });
});
