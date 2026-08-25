import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronDown, ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
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

type PeriodOption = 7 | 30 | 365;
type CountryOption = '' | 'BR' | 'CL';
type RankingTab = 'municipios' | 'estados' | 'paises';

// Portuguese number formatting (1.239 instead of 1,239)
function formatPortugueseNumber(num: number): string {
  return num.toLocaleString('pt-BR');
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
  
  // Issue #186: Default to Brasil, last year (365 days), Municípios tab
  const [period, setPeriod] = useState<PeriodOption>(365);
  const [country, setCountry] = useState<CountryOption>('BR');
  const [rankingTab, setRankingTab] = useState<RankingTab>('municipios');
  const [cityLimit, setCityLimit] = useState<number>(50);
  const [aboutOpen, setAboutOpen] = useState(false);
  const [methodologyOpen, setMethodologyOpen] = useState(false);
  
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

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-12">
              <div className="text-stone-500">{t.rankingsLoading}</div>
            </div>
          )}

          {/* Rankings tables */}
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

              {/* Coverage Table */}
              {coverageData && !isCoverageLoading && (
                <div className="rounded-xl border border-stone-200 bg-white overflow-hidden">
                  <div className="px-6 py-4 border-b border-stone-200">
                    <h2 className="text-lg font-semibold text-stone-900">
                      Cobertura: Arquivo vs Oficial
                    </h2>
                    <p className="text-sm text-stone-500 mt-1">
                      Comparação entre vítimas registradas pelo Arquivo da Violência e dados oficiais do Ministério da Justiça e Segurança Pública. Janela: desde setembro/2025.
                    </p>
                  </div>
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
                          <th className="px-4 py-3 text-right text-xs font-medium text-stone-500 uppercase tracking-wider">
                            Cobertura
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white divide-y divide-stone-200">
                        {coverageData.municipalities.map((muni: CoverageMunicipality) => {
                          const coveragePercent = muni.coverage != null ? (muni.coverage * 100).toFixed(0) : '—';
                          const coverageColor = 
                            muni.coverage == null ? 'text-stone-400' :
                            muni.coverage < 0.5 ? 'text-red-600' :
                            muni.coverage < 0.8 ? 'text-orange-600' :
                            muni.coverage < 1.0 ? 'text-yellow-600' :
                            muni.coverage >= 1.0 ? 'text-green-600' :
                            'text-stone-600';
                          
                          return (
                            <tr key={muni.code} className="hover:bg-stone-50">
                              <td className="px-4 py-3 font-medium text-stone-900">
                                {muni.name}
                              </td>
                              <td className="px-4 py-3 text-center text-stone-700">
                                {muni.uf}
                              </td>
                              <td className="px-4 py-3 text-right text-stone-900">
                                {formatPortugueseNumber(muni.official_victims)}
                              </td>
                              <td className="px-4 py-3 text-right text-stone-900">
                                {formatPortugueseNumber(muni.arquivo_victims)}
                              </td>
                              <td className={cn('px-4 py-3 text-right font-semibold', coverageColor)}>
                                {coveragePercent}%
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
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
