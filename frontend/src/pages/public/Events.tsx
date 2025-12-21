import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { fetchPublicEvents, type PublicEvent } from '@/lib/api';
import { Loader2, ChevronLeft, ChevronRight, MapPin, Users, Clock, Shield, Search, ExternalLink, ChevronDown, ChevronUp } from 'lucide-react';

function formatRelativeTime(dateStr: string) {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 60) return `há ${diffMins} minuto${diffMins !== 1 ? 's' : ''}`;
  if (diffHours < 24) return `há ${diffHours} hora${diffHours !== 1 ? 's' : ''}`;
  if (diffDays === 1) return 'ontem';
  if (diffDays < 7) return `há ${diffDays} dias`;
  
  return date.toLocaleDateString('pt-BR', { day: '2-digit', month: 'short', year: 'numeric' });
}

function EventRow({ event, expanded, onToggle }: { event: PublicEvent; expanded: boolean; onToggle: () => void }) {
  return (
    <>
      <TableRow className="cursor-pointer hover:bg-muted/50" onClick={onToggle}>
        <TableCell className="w-[30px] px-2">
          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </TableCell>
        <TableCell className="w-[100px] px-2">
          <div className="text-xs">{formatRelativeTime(event.created_at)}</div>
        </TableCell>
        <TableCell className="w-[120px] px-2">
          <div className="flex flex-col gap-1">
            {event.homicide_type && (
              <Badge variant="outline" className="text-xs whitespace-nowrap">{event.homicide_type}</Badge>
            )}
            {event.security_force_involved && (
              <Badge variant="destructive" className="gap-1 text-xs whitespace-nowrap">
                <Shield className="h-3 w-3" />
              </Badge>
            )}
          </div>
        </TableCell>
        <TableCell className="min-w-[200px] px-2 !whitespace-normal">
          <div className="font-medium text-sm break-words">{event.title || 'Sem título'}</div>
          {!expanded && event.chronological_description && (
            <div className="text-xs text-muted-foreground line-clamp-2 mt-1">
              {event.chronological_description}
            </div>
          )}
        </TableCell>
        <TableCell className="w-[150px] px-2 !whitespace-normal">
          {event.city && event.state && (
            <div className="text-xs break-words">
              {event.city}, {event.state}
            </div>
          )}
        </TableCell>
        <TableCell className="w-[80px] text-center px-2">
          <div className="text-sm font-medium">{event.victim_count || '-'}</div>
        </TableCell>
        <TableCell className="w-[120px] px-2 hidden md:table-cell !whitespace-normal">
          <div className="text-xs break-words">{event.method_of_death || '-'}</div>
        </TableCell>
        <TableCell className="w-[70px] text-center px-2 text-xs text-muted-foreground hidden lg:table-cell">
          {event.source_count}
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={8} className="bg-muted/30 !whitespace-normal px-4">
            <div className="py-4 space-y-4 max-w-full">
              {/* Detailed Info Grid */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-sm">
                {event.event_date && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Data do Evento</div>
                    <div className="font-medium">
                      {new Date(event.event_date).toLocaleDateString('pt-BR', {
                        day: '2-digit',
                        month: 'long',
                        year: 'numeric'
                      })}
                    </div>
                  </div>
                )}
                {event.time_of_day && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Horário</div>
                    <div className="font-medium">{event.time_of_day}</div>
                  </div>
                )}
                {event.victim_count && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Número de Vítimas</div>
                    <div className="font-medium flex items-center gap-1">
                      <Users className="h-4 w-4" />
                      {event.victim_count}
                    </div>
                  </div>
                )}
                {event.source_count && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Fontes</div>
                    <div className="font-medium">{event.source_count} {event.source_count === 1 ? 'fonte' : 'fontes'}</div>
                  </div>
                )}
              </div>

              {/* Location Details */}
              {(event.city || event.state || event.neighborhood) && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2">Localização Completa</div>
                  <div className="flex items-start gap-2">
                    <MapPin className="h-4 w-4 mt-0.5 text-muted-foreground" />
                    <div className="text-sm">
                      {[event.neighborhood, event.city, event.state].filter(Boolean).join(', ')}
                    </div>
                  </div>
                </div>
              )}

              {/* Type and Method */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-sm">
                {event.homicide_type && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Tipo de Homicídio</div>
                    <Badge variant="outline">{event.homicide_type}</Badge>
                  </div>
                )}
                {event.method_of_death && (
                  <div>
                    <div className="text-xs text-muted-foreground mb-1">Método</div>
                    <div className="font-medium">{event.method_of_death}</div>
                  </div>
                )}
              </div>

              {/* Security Force Badge */}
              {event.security_force_involved && (
                <div>
                  <Badge variant="destructive" className="gap-2">
                    <Shield className="h-4 w-4" />
                    Envolvimento de Forças de Segurança
                  </Badge>
                </div>
              )}

              {/* Victims Summary */}
              {(event.merged_data?.victims || event.victims_summary || event.victim_count) && (
                <div className="bg-background/50 p-4 rounded-lg border">
                  <div className="flex items-center gap-2 mb-3">
                    <Users className="h-5 w-5 text-primary flex-shrink-0" />
                    <div className="font-semibold text-base">Informações sobre as Vítimas</div>
                  </div>
                  <div className="space-y-2">
                    {(() => {
                      // Try to use merged_data.victims first (structured data)
                      const victimsData = event.merged_data?.victims;
                      const identifiableVictims = victimsData?.identifiable_victims;
                      const unidentifiedCount = victimsData?.number_of_unidentified_victims || 0;
                      
                      const elements: JSX.Element[] = [];
                      
                      // Show identifiable victims
                      if (identifiableVictims && Array.isArray(identifiableVictims) && identifiableVictims.length > 0) {
                        identifiableVictims.forEach((victim: any, index: number) => {
                          const parts = [];
                          if (victim.name) parts.push(victim.name);
                          if (victim.age) parts.push(`${victim.age} anos`);
                          if (victim.gender) parts.push(victim.gender);
                          if (victim.occupation) parts.push(victim.occupation);
                          
                          const victimText = parts.join(', ');
                          if (victimText) {
                            elements.push(
                              <div key={`identified-${index}`} className="flex items-start gap-2 text-sm">
                                <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                                <span className="leading-relaxed break-words flex-1">{victimText}</span>
                              </div>
                            );
                          }
                        });
                      }
                      
                      // Show unidentified victims count
                      if (unidentifiedCount > 0) {
                        elements.push(
                          <div key="unidentified" className="flex items-start gap-2 text-sm text-muted-foreground">
                            <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-muted-foreground flex-shrink-0" />
                            <span className="leading-relaxed break-words flex-1 italic">
                              {unidentifiedCount} {unidentifiedCount === 1 ? 'vítima não identificada' : 'vítimas não identificadas'}
                            </span>
                          </div>
                        );
                      }
                      
                      // If we have elements from merged_data, return them
                      if (elements.length > 0) {
                        return elements;
                      }
                      
                      // Fallback to parsing victims_summary
                      if (event.victims_summary) {
                        const sentences = event.victims_summary.split('.');
                        const victimsText = sentences[0];
                        const victims = victimsText.split(/,(?![^()]*\))/);
                        
                        return victims.map((victim, index) => {
                          const cleanedVictim = victim.replace(/^(e|and)\s+/i, '').trim();
                          if (!cleanedVictim) return null;
                          
                          return (
                            <div key={index} className="flex items-start gap-2 text-sm">
                              <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-primary flex-shrink-0" />
                              <span className="leading-relaxed break-words flex-1">{cleanedVictim}</span>
                            </div>
                          );
                        });
                      }
                      
                      // Final fallback - just show victim count if available
                      if (event.victim_count) {
                        return (
                          <div className="flex items-start gap-2 text-sm text-muted-foreground">
                            <div className="mt-1.5 h-1.5 w-1.5 rounded-full bg-muted-foreground flex-shrink-0" />
                            <span className="leading-relaxed break-words flex-1 italic">
                              {event.victim_count} {event.victim_count === 1 ? 'vítima não identificada' : 'vítimas não identificadas'}
                            </span>
                          </div>
                        );
                      }
                      
                      return null;
                    })()}
                  </div>
                </div>
              )}

              {/* Chronological Description */}
              {event.chronological_description && (
                <div>
                  <div className="text-xs text-muted-foreground mb-2">Descrição Cronológica</div>
                  <p className="text-sm leading-relaxed whitespace-pre-wrap break-words">
                    {event.chronological_description}
                  </p>
                </div>
              )}

              {/* Google Maps Link */}
              {event.latitude && event.longitude && (
                <div className="pt-2 border-t">
                  <a
                    href={`https://www.google.com/maps?q=${event.latitude},${event.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <MapPin className="h-4 w-4" />
                    Ver localização no Google Maps
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function Events() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [stateFilter, setStateFilter] = useState('');
  const [typeFilter, setTypeFilter] = useState('');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const perPage = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ['public-events', page, perPage, search, stateFilter, typeFilter],
    queryFn: () => fetchPublicEvents(page, perPage, {
      search: search || undefined,
      state: stateFilter || undefined,
      type: typeFilter || undefined,
    }),
    placeholderData: (prev) => prev,
  });

  return (
    <div className="container mx-auto px-6 py-12 max-w-5xl">
      <div className="mb-8">
        <h1 className="text-4xl font-bold tracking-tight mb-2">Linha do Tempo</h1>
        <p className="text-lg text-muted-foreground">
          Registro cronológico de mortes violentas no Brasil
        </p>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardContent className="pt-6">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder="Buscar por local ou descrição..."
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setPage(1);
                }}
                className="pl-9"
              />
            </div>
            <select
              value={stateFilter}
              onChange={(e) => {
                setStateFilter(e.target.value);
                setPage(1);
              }}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Todos os estados</option>
              <option value="SP">São Paulo</option>
              <option value="RJ">Rio de Janeiro</option>
              <option value="MG">Minas Gerais</option>
              <option value="BA">Bahia</option>
              <option value="PR">Paraná</option>
              <option value="RS">Rio Grande do Sul</option>
              <option value="PE">Pernambuco</option>
              <option value="CE">Ceará</option>
              {/* Add more states as needed */}
            </select>
            <select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value);
                setPage(1);
              }}
              className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">Todos os tipos</option>
              <option value="Homicídio">Homicídio</option>
              <option value="Homicídio Qualificado">Homicídio Qualificado</option>
              <option value="Tentativa de Homicídio">Tentativa de Homicídio</option>
              <option value="Outro">Outro</option>
            </select>
          </div>
        </CardContent>
      </Card>

      {/* Results Count */}
      {data && (
        <div className="mb-4 text-sm text-muted-foreground">
          Mostrando {data.total.toLocaleString()} {data.total === 1 ? 'evento' : 'eventos'}
        </div>
      )}

      {/* Events List */}
      {isLoading ? (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : error ? (
        <div className="text-center py-8 text-muted-foreground">
          Erro ao carregar eventos. Tente novamente.
        </div>
      ) : !data?.items.length ? (
        <div className="text-center py-12 text-muted-foreground">
          <p className="text-lg mb-2">Nenhum evento encontrado</p>
          <p className="text-sm">Tente ajustar os filtros</p>
        </div>
      ) : (
        <>
          <Card className="mb-6 overflow-hidden">
            <CardContent className="p-0 overflow-x-auto">
              <Table className="table-auto">
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[30px]"></TableHead>
                    <TableHead className="w-[100px]">Data</TableHead>
                    <TableHead className="w-[120px]">Tipo</TableHead>
                    <TableHead className="min-w-[200px]">Título</TableHead>
                    <TableHead className="w-[150px]">Local</TableHead>
                    <TableHead className="w-[80px] text-center">Vítimas</TableHead>
                    <TableHead className="w-[120px] hidden md:table-cell">Método</TableHead>
                    <TableHead className="w-[70px] text-center hidden lg:table-cell">Fontes</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((event) => (
                    <EventRow
                      key={event.id}
                      event={event}
                      expanded={expandedId === event.id}
                      onToggle={() => setExpandedId(expandedId === event.id ? null : event.id)}
                    />
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>

          {/* Pagination */}
          <div className="flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Página {data.page} de {data.pages}
            </p>
            <div className="flex gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
              >
                <ChevronLeft className="h-4 w-4" />
                Anterior
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                disabled={page >= data.pages}
              >
                Próxima
                <ChevronRight className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

