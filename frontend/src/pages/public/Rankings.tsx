import { useState, useMemo, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ArrowLeft, Download, Search } from 'lucide-react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { fetchRankings, fetchCoverageStats } from '@/lib/api';
import type { RankingRow, CoverageMunicipality } from '@/lib/api';
import { useI18n } from '@/contexts/I18nContext';
import { ArchiveLogo } from '@/components/portal/ArchiveLogo';
import { LeftRail } from '@/components/portal/LeftRail';
import { AboutModal } from '@/components/portal/AboutModal';
import { MethodologyPanel } from '@/components/portal/MethodologyPanel';
import { useIsMobile } from '@/hooks/useMediaQuery';
import { cn } from '@/lib/utils';
import { formatTypeStatLabel } from '@/lib/taxonomy';
import { translateMethod } from '@/lib/i18n';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PlaceSearch, type PlaceOption } from '@/components/portal/PlaceSearch';
import { PlaceCard, type PlaceData } from '@/components/portal/PlaceCard';

type PeriodOption = 7 | 30 | 365;
type CountryOption = '' | 'BR' | 'CL';
type RankingTab = 'municipios' | 'estados' | 'paises';

// Portuguese number formatting (1.239 instead of 1,239)
function formatPortugueseNumber(num: number): string {
  return num.toLocaleString('pt-BR');
}

// Skeleton loading components
function SkeletonCard() {
  return (
    <div data-testid="skeleton-card" className="rounded-xl border border-stone-200 bg-white p-6 space-y-4 animate-pulse">
      <div className="h-6 bg-stone-200 rounded w-3/4"></div>
      <div className="h-4 bg-stone-200 rounded w-1/2"></div>
      <div className="h-12 bg-stone-200 rounded w-full"></div>
      <div className="h-4 bg-stone-200 rounded w-2/3"></div>
    </div>
  );
}

function SkeletonTable() {
  return (
    <div data-testid="skeleton-table" className="rounded-xl border border-stone-200 bg-white overflow-hidden animate-pulse">
      <div className="px-6 py-4 border-b border-stone-200">
        <div className="h-6 bg-stone-200 rounded w-1/3"></div>
      </div>
      <div className="p-6 space-y-3">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex gap-4">
            <div className="h-4 bg-stone-200 rounded flex-1"></div>
            <div className="h-4 bg-stone-200 rounded w-20"></div>
            <div className="h-4 bg-stone-200 rounded w-20"></div>
          </div>
        ))}
      </div>
    </div>
  );
}

interface CoverageTableProps {
  municipalities: CoverageMunicipality[];
  isEmpty?: boolean;
}

function CoverageTable({ municipalities, isEmpty = false }: CoverageTableProps) {
  const isMobile = useIsMobile();
  const [searchTerm, setSearchTerm] = useState('');
  const [showCoverage, setShowCoverage] = useState(false);
  const [perPage, setPerPage] = useState(25);
  const [currentPage, setCurrentPage] = useState(1);

  // Three distinct empty marks (issue #187):
  // 1. Official not published (no official data) → "N/P" (not published)
  // 2. Official published zero (has official data, sum=0) → "0"
  // 3. Arquivo found none → "—" with tooltip
  const renderOfficialMark = (official: number, published: boolean) => {
    if (!published) {
      // Official not published (no data in OfficialViolenceCount)
      return <span className="text-stone-400" title="Dados oficiais não publicados">N/P</span>;
    }
    if (official === 0) {
      // Official published zero (has data, sum=0)
      return <span className="text-stone-700">0</span>;
    }
    return formatPortugueseNumber(official);
  };

  const renderArquivoMark = (arquivo: number) => {
    if (arquivo === 0) {
      // Arquivo found none
      return <span className="text-stone-400" title="Sem registro no Arquivo neste período">—</span>;
    }
    return formatPortugueseNumber(arquivo);
  };

  // Filter municipalities by search term
  const filteredMunicipalities = searchTerm
    ? municipalities.filter(muni =>
        muni.name.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : municipalities;

  // Calculate pagination
  const totalPages = Math.ceil(filteredMunicipalities.length / perPage);
  const startIndex = (currentPage - 1) * perPage;
  const endIndex = startIndex + perPage;
  const paginatedMunicipalities = filteredMunicipalities.slice(startIndex, endIndex);

  // Check if any municipality has coverage > 1
  const hasOverCoverage = municipalities.some(m => m.coverage != null && m.coverage > 1.0);

  // Reset to page 1 when search or perPage changes
  const handleSearchChange = (value: string) => {
    setSearchTerm(value);
    setCurrentPage(1);
  };

  const handlePerPageChange = (value: number) => {
    setPerPage(value);
    setCurrentPage(1);
  };

  // Empty state for Chile or no data
  if (isEmpty || municipalities.length === 0) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
        <div className="px-6 py-4 border-b border-stone-200">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h2 className="text-lg font-semibold text-stone-900">
                Cobertura: Arquivo vs Oficial
              </h2>
              <p className="text-sm text-stone-500 mt-1">
                Comparação entre vítimas registradas pelo Arquivo da Violência e dados oficiais do Ministério da Justiça e Segurança Pública. Janela: desde setembro/2025.
              </p>
            </div>
            <a
              href="/api/public/stats/coverage/download"
              download
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors"
            >
              <Download className="h-4 w-4" />
              Baixar oficial
            </a>
          </div>
        </div>
        <div className="px-6 py-12 text-center">
          <p className="text-stone-600 text-sm">
            Dados de cobertura não disponíveis para este país ou período.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      {/* Header */}
      <div className="px-6 py-4 border-b border-stone-200">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h2 className="text-lg font-semibold text-stone-900">
              Cobertura: Arquivo vs Oficial
            </h2>
            <p className="text-sm text-stone-500 mt-1">
              Comparação entre vítimas registradas pelo Arquivo da Violência e dados oficiais do Ministério da Justiça e Segurança Pública. Janela: desde setembro/2025.
            </p>
          </div>
          <a
            href="/api/public/stats/coverage/download"
            download
            className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-blue-600 hover:text-blue-700 border border-blue-600 rounded-lg hover:bg-blue-50 transition-colors"
          >
            <Download className="h-4 w-4" />
            Baixar oficial
          </a>
        </div>

        {/* Search and filters */}
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-stone-400" />
            <input
              type="text"
              placeholder="Buscar município..."
              value={searchTerm}
              onChange={(e) => handleSearchChange(e.target.value)}
              className="w-full pl-10 pr-4 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <button
            onClick={() => setShowCoverage(!showCoverage)}
            className={cn(
              'px-4 py-2 text-sm font-medium rounded-lg transition-colors whitespace-nowrap',
              showCoverage
                ? 'bg-blue-600 text-white'
                : 'bg-stone-100 text-stone-700 hover:bg-stone-200'
            )}
          >
            {showCoverage ? 'Ocultar cobertura' : 'Mostrar cobertura'}
          </button>
          <select
            value={perPage}
            onChange={(e) => handlePerPageChange(Number(e.target.value))}
            className="px-4 py-2 border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            <option value={25}>25 por página</option>
            <option value={50}>50 por página</option>
          </select>
        </div>
      </div>

      {/* Table or Cards (mobile) */}
      {isMobile ? (
        // Mobile: Stacked cards
        <div className="divide-y divide-stone-200">
          {paginatedMunicipalities.length === 0 ? (
            <div className="px-4 py-8 text-center text-stone-500">
              Nenhum município encontrado.
            </div>
          ) : (
            paginatedMunicipalities.map((muni) => {
              const coveragePercent = muni.coverage != null 
                ? `${(muni.coverage * 100).toFixed(0)}%` 
                : '—';
              
              return (
                <div key={muni.code} data-testid="coverage-card" className="px-4 py-4 hover:bg-stone-50">
                  <div className="flex justify-between items-start mb-2">
                    <div className="font-medium text-stone-900">{muni.name}</div>
                    <div className="text-sm text-stone-600 ml-2">{muni.uf}</div>
                  </div>
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div>
                      <div className="text-xs text-stone-500 mb-1">Oficial</div>
                      <div className="text-stone-900 font-medium">
                        {renderOfficialMark(muni.official_victims, muni.official_published)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-stone-500 mb-1">Arquivo</div>
                      <div className="text-stone-900 font-medium">
                        {renderArquivoMark(muni.arquivo_victims)}
                      </div>
                    </div>
                    {showCoverage && (
                      <div className="col-span-2">
                        <div className="text-xs text-stone-500 mb-1">Cobertura</div>
                        <div className="text-stone-700 font-medium">{coveragePercent}</div>
                      </div>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>
      ) : (
        // Desktop: Table
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-stone-50 border-b border-stone-200">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-stone-500 uppercase tracking-wider">
                  Município
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-stone-500 uppercase tracking-wider">
                  UF
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                  Oficial
                </th>
                <th className="px-4 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                  Arquivo
                </th>
                {showCoverage && (
                  <th className="px-4 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                    Cobertura
                  </th>
                )}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-stone-200">
              {paginatedMunicipalities.length === 0 ? (
                <tr>
                  <td colSpan={showCoverage ? 5 : 4} className="px-4 py-8 text-center text-stone-500">
                    Nenhum município encontrado.
                  </td>
                </tr>
              ) : (
                paginatedMunicipalities.map((muni) => {
                  // Fix: Don't append % to null coverage
                  const coveragePercent = muni.coverage != null 
                    ? `${(muni.coverage * 100).toFixed(0)}%` 
                    : '—';
                  
                  return (
                    <tr key={muni.code} className="hover:bg-stone-50">
                      <td className="px-4 py-3 font-medium text-stone-900">
                        {muni.name}
                      </td>
                      <td className="px-4 py-3 text-center text-stone-700">
                        {muni.uf}
                      </td>
                      <td className="px-4 py-3 text-right text-stone-900">
                        {renderOfficialMark(muni.official_victims, muni.official_published)}
                      </td>
                      <td className="px-4 py-3 text-right text-stone-900">
                        {renderArquivoMark(muni.arquivo_victims)}
                      </td>
                      {showCoverage && (
                        <td className="px-4 py-3 text-right text-stone-700">
                          {coveragePercent}
                        </td>
                      )}
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {filteredMunicipalities.length > 0 && (
        <div className="px-6 py-4 border-t border-stone-200 flex items-center justify-between">
          <div className="text-sm text-stone-600">
            Mostrando {startIndex + 1}-{Math.min(endIndex, filteredMunicipalities.length)} de {filteredMunicipalities.length}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 text-sm font-medium text-stone-700 border border-stone-300 rounded hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Anterior
            </button>
            <div className="flex items-center gap-1">
              <span className="text-sm text-stone-600">
                Página {currentPage} de {totalPages}
              </span>
            </div>
            <button
              onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 text-sm font-medium text-stone-700 border border-stone-300 rounded hover:bg-stone-50 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Próxima
            </button>
          </div>
        </div>
      )}

      {/* Footnote for >100% coverage - show whenever coverage > 1.0 exists, not only when showCoverage is on */}
      {hasOverCoverage && (
        <div className="px-6 py-4 border-t border-stone-200 bg-stone-50">
          <p className="text-xs text-stone-600">
            <strong>Nota:</strong> Cobertura acima de 100% significa que o Arquivo da Violência contou mais vítimas, naquele município e naquele período, do que o Formulário 1 municipal do Ministério da Justiça e Segurança Pública — não é erro de conta.
          </p>
        </div>
      )}
    </div>
  );
}

interface RankingTableProps {
  title: string;
  rows: RankingRow[];
  labelField: keyof RankingRow;
  onRowClick?: (value: string) => void;
  emptyMessage?: string;
  showRateColumns?: boolean;
}

function RankingTable({ title, rows, labelField, onRowClick, emptyMessage, showRateColumns = false }: RankingTableProps) {
  const { t, lang } = useI18n();
  // Issue #186: Default to collapsed (showing top 10), not expanded
  const [expanded, setExpanded] = useState(false);
  
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-stone-200 bg-white p-6">
        <h2 className="mb-2 text-lg font-semibold text-stone-900">{title}</h2>
        <p className="text-sm text-stone-500">{emptyMessage || t.emptyArea}</p>
      </div>
    );
  }

  // Show top 10 when collapsed, all when expanded
  const displayRows = expanded ? rows : rows.slice(0, 10);
  const hasRateData = showRateColumns && rows.some(r => r.rate_per_100k != null);
  
  // Helper to format numbers in Portuguese style (1.239 instead of 1,239)
  const formatNum = (num: number) => formatPortugueseNumber(num);

  return (
    <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
      <div className="px-6 py-4 border-b border-stone-200">
        <h2 className="text-lg font-semibold text-stone-900">{title}</h2>
        <p className="text-sm text-stone-500 mt-1">{rows.length} {rows.length === 1 ? 'item' : 'itens'}</p>
      </div>
      
      <div className="overflow-x-auto">
          <table className="w-full">
            <thead className="bg-stone-50 border-t border-stone-200">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-stone-500 uppercase tracking-wider">
                  #
                </th>
                <th className="px-6 py-3 text-left text-xs font-medium text-stone-500 uppercase tracking-wider">
                  {t.rankingsPlace}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                  {t.rankingsVictimCount}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                  {t.rankingsEventCount}
                </th>
                <th className="px-6 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                  {t.rankingsShare}
                </th>
                {hasRateData && (
                  <>
                    <th className="px-6 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                      Taxa / 100k
                    </th>
                    <th className="px-6 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                      População
                    </th>
                  </>
                )}
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-stone-200">
              {displayRows.map((row, idx) => {
                const label = row[labelField] as string || 'N/A';
                let displayLabel = labelField === 'type' ? formatTypeStatLabel(label, lang) : 
                                   labelField === 'method' ? translateMethod(label, lang) : 
                                   label;
                
                // For cities, append UF if available
                if (labelField === 'city' && row.state_abbrev) {
                  displayLabel = `${displayLabel}, ${row.state_abbrev}`;
                }
                
                return (
                  <tr
                    key={idx}
                    className={cn('hover:bg-stone-50 transition-colors', onRowClick && 'cursor-pointer')}
                    onClick={() => onRowClick && onRowClick(label)}
                  >
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-stone-500">
                      {idx + 1}
                    </td>
                    <td className="px-6 py-4 text-sm font-medium text-stone-900">
                      {displayLabel}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-stone-900">
                      {formatNum(row.victim_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-stone-700">
                      {formatNum(row.event_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-stone-700">
                      {row.victim_share.toFixed(1).replace('.', ',')}%
                    </td>
                    {hasRateData && (
                      <>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-stone-900 font-semibold">
                          {row.rate_per_100k != null ? row.rate_per_100k.toFixed(2).replace('.', ',') : '—'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-stone-700">
                          {row.population != null ? formatNum(row.population) : '—'}
                        </td>
                      </>
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      
      {/* Ver mais button - show when collapsed and there are more than 10 rows */}
      {!expanded && rows.length > 10 && (
        <div className="px-6 py-3 bg-stone-50 border-t border-stone-200 text-center">
          <button
            onClick={() => setExpanded(true)}
            className="text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            Ver mais ({rows.length - 10} itens)
          </button>
        </div>
      )}
      
      {/* Collapse button - show when expanded */}
      {expanded && rows.length > 10 && (
        <div className="px-6 py-3 bg-stone-50 border-t border-stone-200 text-center">
          <button
            onClick={() => setExpanded(false)}
            className="text-sm text-blue-600 hover:text-blue-700 font-medium"
          >
            Ver menos
          </button>
        </div>
      )}
    </div>
  );
}

export function Rankings() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const [searchParams, setSearchParams] = useSearchParams();
  
  // Issue #186: Default to Brasil, last year (365 days), Municípios tab
  const [period, setPeriod] = useState<PeriodOption>(365);
  const [country, setCountry] = useState<CountryOption>('BR');
  const [rankingTab, setRankingTab] = useState<RankingTab>('municipios');
  const [cityLimit, setCityLimit] = useState<number>(50);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  
  // Issue #185: Place search state (default to Brasil)
  const [selectedPlace, setSelectedPlace] = useState<PlaceOption>({
    name: 'Brasil',
    type: 'country',
    displayName: 'Brasil',
  });
  
  // Issue #189: Read period and country from URL on mount (one-time only)
  useEffect(() => {
    try {
      const periodParam = searchParams.get('period');
      if (periodParam) {
        if (periodParam === '7') setPeriod(7);
        else if (periodParam === '30') setPeriod(30);
        else if (periodParam === '365') setPeriod(365);
      }
      
      const countryParam = searchParams.get('country');
      if (countryParam !== null) {
        if (countryParam === 'BR') setCountry('BR');
        else if (countryParam === 'CL') setCountry('CL');
        else if (countryParam === '') setCountry('');
      }
    } catch (e) {
      // Use defaults
    }
    
    // Mark as loaded after reading URL
    setInitialLoad(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run once on mount
  
  // Issue #189: Sync URL params when period or country changes (skip initial render)
  useEffect(() => {
    if (initialLoad) return;
    
    try {
      const newParams = new URLSearchParams(searchParams);
      newParams.set('period', period.toString());
      if (country) {
        newParams.set('country', country);
      } else {
        newParams.delete('country');
      }
      setSearchParams(newParams, { replace: true });
    } catch (e) {
      // Ignore URL sync errors in test environments
    }
  }, [period, country, initialLoad, searchParams, setSearchParams]);
  
  // Reset city limit when period or country changes
  const handlePeriodChange = (newPeriod: PeriodOption) => {
    setPeriod(newPeriod);
    setCityLimit(50);
  };
  
  const handleCountryChange = (newCountry: CountryOption) => {
    setCountry(newCountry);
    setCityLimit(50);
  };

  const { data, isLoading } = useQuery({
    queryKey: ['rankings', period, country, cityLimit],
    queryFn: () => fetchRankings({ days: period, country: country || undefined, cityLimit }),
  });

  const { data: coverageData, isLoading: isCoverageLoading } = useQuery({
    queryKey: ['coverageStats'],
    queryFn: fetchCoverageStats,
  });

  const periodOptions: { value: PeriodOption; label: string }[] = [
    { value: 7, label: t.rankingsLast7Days },
    { value: 30, label: t.rankingsLast30Days },
    { value: 365, label: t.rankingsLast365Days },
  ];

  const countryOptions: { value: CountryOption; label: string }[] = [
    { value: '', label: t.rankingsAllCountries },
    { value: 'BR', label: 'Brasil' },
    { value: 'CL', label: 'Chile' },
  ];

  // Issue #185: Build place options for typeahead
  const placeOptions = useMemo((): PlaceOption[] => {
    if (!data) return [];
    
    const options: PlaceOption[] = [
      { name: 'Brasil', type: 'country', displayName: 'Brasil' },
    ];
    
    data.states.forEach(state => {
      // Only add states that have a defined state field
      if (!state.state) return;
      
      let uf = state.state;
      if (state.state.length > 2) {
        const cityInState = data.cities.find(c => c.state === state.state);
        if (cityInState?.state_abbrev) {
          uf = cityInState.state_abbrev;
        }
      }
      
      options.push({
        name: state.state,
        type: 'state',
        uf,
        displayName: state.state,
      });
    });
    
    data.cities.forEach(city => {
      // Only add cities that have a defined city name
      if (!city.city) return;
      
      options.push({
        name: city.city,
        type: 'municipality',
        state: city.state,
        uf: city.state_abbrev || undefined,
        displayName: city.state_abbrev ? `${city.city}, ${city.state_abbrev}` : city.city,
      });
    });
    
    return options;
  }, [data]);

  // Issue #185: Build place data for the selected place card
  const placeData = useMemo((): PlaceData | null => {
    if (!data) return null;
    
    if (selectedPlace.type === 'country' && selectedPlace.name === 'Brasil') {
      let officialVictims: number | null = null;
      let officialAvailable = false;
      
      if (period === 365 && coverageData && coverageData.municipalities.length > 0) {
        officialVictims = coverageData.municipalities.reduce(
          (sum, muni) => sum + muni.official_victims,
          0
        );
        officialAvailable = true;
      }
      
      return {
        name: 'Brasil',
        type: 'country',
        arquivoVictims: data.total_victims,
        officialVictims: officialAvailable ? officialVictims : null,
        officialAvailable,
        lastUpdated: data.last_updated || new Date().toISOString(),
        period,
        officialWindowStart: coverageData?.window_start,
      };
    } else if (selectedPlace.type === 'state') {
      const stateRow = data.states.find(s => s.state === selectedPlace.name);
      if (!stateRow) return null;
      
      let officialVictims: number | null = null;
      let officialAvailable = false;
      
      if (period === 365 && coverageData && selectedPlace.uf) {
        const stateMunis = coverageData.municipalities.filter(
          muni => muni.uf === selectedPlace.uf
        );
        if (stateMunis.length > 0) {
          officialVictims = stateMunis.reduce((sum, muni) => sum + muni.official_victims, 0);
          officialAvailable = true;
        }
      }
      
      return {
        name: selectedPlace.name,
        type: 'state',
        arquivoVictims: stateRow.victim_count,
        officialVictims: officialAvailable ? officialVictims : null,
        officialAvailable,
        lastUpdated: data.last_updated || new Date().toISOString(),
        period,
        officialWindowStart: coverageData?.window_start,
      };
    } else if (selectedPlace.type === 'municipality') {
      const cityRow = data.cities.find(c => c.city === selectedPlace.name);
      if (!cityRow) return null;
      
      let officialVictims: number | null = null;
      let officialAvailable = false;
      
      if (period === 365 && coverageData) {
        const muniOfficial = coverageData.municipalities.find(
          muni => muni.name === selectedPlace.name && muni.uf === selectedPlace.uf
        );
        if (muniOfficial) {
          officialVictims = muniOfficial.official_victims;
          officialAvailable = true;
        }
      }
      
      return {
        name: selectedPlace.displayName,
        type: 'municipality',
        arquivoVictims: cityRow.victim_count,
        officialVictims: officialAvailable ? officialVictims : null,
        officialAvailable,
        lastUpdated: data.last_updated || new Date().toISOString(),
        period,
        officialWindowStart: coverageData?.window_start,
      };
    }
    
    return null;
  }, [data, coverageData, selectedPlace, period]);

  const handleCityClick = (city: string) => {
    // Deep link to map filtered to this city
    navigate(`/?city=${encodeURIComponent(city)}`);
  };

  const handleStateClick = (state: string) => {
    // Deep link to map filtered to this state
    navigate(`/?state=${encodeURIComponent(state)}`);
  };

  const handleOpenMethodology = () => {
    setAboutOpen(false);
    setMethodologyOpen(true);
  };

  const handleSetMode = () => {
    // Navigate to data page when user clicks the data link in methodology
    navigate('/dados');
  };

  return (
    <div className="flex h-screen w-full overflow-hidden" style={{ background: 'var(--stone-50)' }}>
      <LeftRail onAbout={() => setAboutOpen(true)} onMethodology={() => setMethodologyOpen(true)} />
      
      <main className="flex-1 overflow-y-auto">
        <div className="max-w-6xl mx-auto px-4 py-8 md:px-8 md:py-12">
          {/* Header */}
          <div className="mb-8">
            <button
              onClick={() => navigate('/')}
              className="inline-flex items-center gap-2 text-sm text-stone-600 hover:text-stone-900 mb-4"
            >
              <ArrowLeft className="h-4 w-4" />
              {t.back}
            </button>
            
            <div className="flex items-center gap-4 mb-4">
              {isMobile && (
                <div className="flex items-center justify-center rounded-lg px-1 py-1" style={{ background: 'rgba(0,0,0,0.08)' }}>
                  <ArchiveLogo size={32} variant="onLight" mark="monogram" />
                </div>
              )}
              <div>
                <h1 className="text-3xl font-bold text-stone-900">{t.rankingsTitle}</h1>
                <p className="text-stone-600 mt-1">{t.rankingsIntro}</p>
              </div>
            </div>
          </div>

          {/* Filters */}
          <div className="mb-6 flex flex-col sm:flex-row gap-4">
            <div>
              <label className="block text-sm font-medium text-stone-700 mb-2">
                {t.fTemporal}
              </label>
              <div className="flex gap-2">
                {periodOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handlePeriodChange(option.value)}
                    className={cn(
                      'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                      period === option.value
                        ? 'bg-blue-600 text-white'
                        : 'bg-white text-stone-700 border border-stone-300 hover:bg-stone-50'
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-stone-700 mb-2">
                {t.rankingsFilterCountry}
              </label>
              <div className="flex gap-2">
                {countryOptions.map((option) => (
                  <button
                    key={option.value}
                    onClick={() => handleCountryChange(option.value)}
                    className={cn(
                      'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                      country === option.value
                        ? 'bg-blue-600 text-white'
                        : 'bg-white text-stone-700 border border-stone-300 hover:bg-stone-50'
                    )}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Issue #185: Place search and card (above the fold) */}
          {!isLoading && data && (
            <div className="mb-8 space-y-4">
              <PlaceSearch
                places={placeOptions}
                selectedPlace={selectedPlace}
                onSelectPlace={setSelectedPlace}
                placeholder="Busque um município ou estado"
              />
              {placeData && (
                <PlaceCard placeData={placeData} />
              )}
            </div>
          )}

          {/* Issue #189: Skeleton loading state (not blank page) */}
          {isLoading && (
            <div className="mb-8 space-y-4">
              <SkeletonCard />
            </div>
          )}

          {/* Rankings tables */}
          {isLoading && (
            <div className="space-y-6">
              {/* Summary skeleton */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <SkeletonCard />
                <SkeletonCard />
              </div>
              <SkeletonTable />
            </div>
          )}

          {data && (
            <div className="space-y-6">
              {/* Summary */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="text-sm text-stone-500 mb-1">{t.rankingsVictimCount}</div>
                  <div className="text-3xl font-bold text-stone-900">{formatPortugueseNumber(data.total_victims)}</div>
                </div>
                <div className="rounded-xl border border-stone-200 bg-white p-6">
                  <div className="text-sm text-stone-500 mb-1">{t.rankingsEventCount}</div>
                  <div className="text-3xl font-bold text-stone-900">{formatPortugueseNumber(data.total_events)}</div>
                </div>
              </div>

              {/* Rankings Tabs - Issue #186: Municípios | Estados | Países */}
              <Tabs value={rankingTab} onValueChange={(v) => setRankingTab(v as RankingTab)} className="w-full">
                <TabsList className="grid w-full grid-cols-3">
                  <TabsTrigger value="municipios">Municípios</TabsTrigger>
                  <TabsTrigger value="estados">Estados</TabsTrigger>
                  <TabsTrigger value="paises">Países</TabsTrigger>
                </TabsList>

                <TabsContent value="municipios" className="mt-6">
                  <RankingTable
                    title={t.rankingsCities}
                    rows={data.cities}
                    labelField="city"
                    onRowClick={handleCityClick}
                    emptyMessage="Nenhuma cidade com eventos no período selecionado."
                    showRateColumns={true}
                  />
                  
                  {/* Show More Cities button */}
                  {data.cities.length === cityLimit && cityLimit < 500 && (
                    <div className="rounded-xl border border-stone-200 bg-white p-4 text-center mt-4">
                      <button
                        onClick={() => setCityLimit(prev => Math.min(prev + 100, 500))}
                        className="text-sm text-blue-600 hover:text-blue-700 font-medium"
                      >
                        Mostrar mais cidades ({cityLimit} de ~{cityLimit + 100}+)
                      </button>
                    </div>
                  )}
                </TabsContent>

                <TabsContent value="estados" className="mt-6">
                  <RankingTable
                    title={t.rankingsStates}
                    rows={data.states}
                    labelField="state"
                    onRowClick={handleStateClick}
                    emptyMessage="Nenhum estado/região com eventos no período selecionado."
                    showRateColumns={true}
                  />
                </TabsContent>

                <TabsContent value="paises" className="mt-6">
                  {/* Countries - only show when not filtering by country */}
                  {!country && data.countries.length > 0 && (
                    <RankingTable
                      title={t.rankingsCountries}
                      rows={data.countries}
                      labelField="country"
                      emptyMessage="Nenhum país com eventos no período selecionado."
                    />
                  )}
                  {country && (
                    <div className="rounded-xl border border-stone-200 bg-white p-6">
                      <p className="text-sm text-stone-500">Filtrando por país específico. Remova o filtro para ver todos os países.</p>
                    </div>
                  )}
                </TabsContent>
              </Tabs>

              {/* Coverage Table - Issue #189: Show empty state for Chile */}
              {coverageData && !isCoverageLoading && (
                <CoverageTable 
                  municipalities={coverageData.municipalities}
                  isEmpty={country === 'CL' && coverageData.municipalities.length === 0}
                />
              )}
            </div>
          )}
        </div>
      </main>

      <AboutModal open={aboutOpen} onClose={() => setAboutOpen(false)} onOpenMethodology={handleOpenMethodology} />
      <MethodologyPanel open={methodologyOpen} onClose={() => setMethodologyOpen(false)} onSetMode={handleSetMode} />
    </div>
  );
}
