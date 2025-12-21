import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchUniqueEvents, type UniqueEvent } from '@/lib/api';
import { 
  Loader2, ChevronLeft, ChevronRight, MapPin, CheckCircle, ExternalLink,
  Crosshair, Calendar, Users, FileText, Globe, Navigation, Shield
} from 'lucide-react';
import {
  DetailSidebar,
  DetailField,
  DetailSection,
  DetailTextBlock,
  DetailJson,
} from '@/components/DetailSidebar';

function formatDate(dateStr: string | null) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'long',
    year: 'numeric',
  });
}

function formatDateTime(dateStr: string | null) {
  if (!dateStr) return null;
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatShortDate(dateStr: string | null) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
  });
}

export function UniqueEvents() {
  const [page, setPage] = useState(1);
  const [selectedEvent, setSelectedEvent] = useState<UniqueEvent | null>(null);
  const perPage = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ['unique-events', page, perPage],
    queryFn: () => fetchUniqueEvents(page, perPage),
    placeholderData: (prev) => prev,
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Unique Events</h1>
        <p className="text-muted-foreground">Deduplicated and enriched events</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>All Unique Events</span>
            {data && (
              <span className="text-sm font-normal text-muted-foreground">
                {data.total.toLocaleString()} total
              </span>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="text-center py-8 text-muted-foreground">
              Failed to load unique events. Is the backend running?
            </div>
          ) : !data?.items.length ? (
            <div className="text-center py-8 text-muted-foreground">
              No unique events found. Run the enrichment pipeline to deduplicate events.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[60px]">ID</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Location</TableHead>
                    <TableHead>Date</TableHead>
                    <TableHead className="text-center">Victims</TableHead>
                    <TableHead className="text-center">Sources</TableHead>
                    <TableHead className="text-center">Geo</TableHead>
                    <TableHead className="text-center">✓</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((event: UniqueEvent) => (
                    <TableRow
                      key={event.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setSelectedEvent(event)}
                    >
                      <TableCell className="font-mono text-xs">{event.id}</TableCell>
                      <TableCell className="max-w-[250px] truncate" title={event.title || undefined}>
                        {event.title || '—'}
                      </TableCell>
                      <TableCell>
                        {event.homicide_type ? (
                          <Badge variant="outline" className="text-xs">
                            {event.homicide_type.replace('Homicídio ', '').replace('Tentativa de ', 'Tent. ')}
                          </Badge>
                        ) : (
                          '—'
                        )}
                      </TableCell>
                      <TableCell className="text-sm max-w-[180px] truncate">
                        {[event.neighborhood, event.city].filter(Boolean).join(', ') || '—'}
                      </TableCell>
                      <TableCell className="text-sm">{formatShortDate(event.event_date)}</TableCell>
                      <TableCell className="text-center font-medium">{event.victim_count ?? '—'}</TableCell>
                      <TableCell className="text-center">
                        <Badge variant="secondary" className="text-xs">{event.source_count}</Badge>
                      </TableCell>
                      <TableCell className="text-center">
                        {event.latitude && event.longitude ? (
                          <MapPin className="h-4 w-4 text-emerald-600 mx-auto" />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                      <TableCell className="text-center">
                        {event.confirmed ? (
                          <CheckCircle className="h-4 w-4 text-emerald-600 mx-auto" />
                        ) : (
                          <span className="text-muted-foreground">—</span>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-muted-foreground">
                  Page {data.page} of {data.pages}
                </p>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    <ChevronLeft className="h-4 w-4" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                    disabled={page >= data.pages}
                  >
                    Next
                    <ChevronRight className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Detail Sidebar */}
      <DetailSidebar
        open={!!selectedEvent}
        onOpenChange={(open) => !open && setSelectedEvent(null)}
        title={`Unique Event #${selectedEvent?.id}`}
        subtitle={selectedEvent?.title || undefined}
        badge={
          selectedEvent && (
            <div className="flex gap-2 shrink-0">
              {selectedEvent.confirmed ? (
                <Badge variant="default" className="bg-emerald-600">
                  <CheckCircle className="h-3 w-3 mr-1" />
                  Confirmado
                </Badge>
              ) : (
                <Badge variant="secondary">Pendente</Badge>
              )}
              <Badge variant="outline">{selectedEvent.source_count} fontes</Badge>
            </div>
          )
        }
      >
        {selectedEvent && (
          <>
            <DetailSection title="Classificação" icon={<Crosshair className="h-3.5 w-3.5" />}>
              <DetailField 
                label="Tipo de Homicídio" 
                value={
                  selectedEvent.homicide_type && (
                    <Badge variant="outline" className="font-normal">
                      {selectedEvent.homicide_type}
                    </Badge>
                  )
                } 
              />
              <DetailField label="Método" value={selectedEvent.method_of_death} />
              <DetailField 
                label="Forças de Segurança" 
                value={
                  selectedEvent.security_force_involved === true ? (
                    <Badge variant="destructive" className="font-normal">
                      <Shield className="h-3 w-3 mr-1" />
                      Envolvidas
                    </Badge>
                  ) : selectedEvent.security_force_involved === false ? (
                    'Não envolvidas'
                  ) : null
                } 
              />
            </DetailSection>

            <DetailSection title="Localização" icon={<MapPin className="h-3.5 w-3.5" />}>
              <DetailField label="País" value={selectedEvent.country} />
              <DetailField label="Estado" value={selectedEvent.state} />
              <DetailField label="Cidade" value={selectedEvent.city} />
              <DetailField label="Bairro" value={selectedEvent.neighborhood} />
              <DetailField label="Rua" value={selectedEvent.street} className="col-span-2" />
              <DetailField label="Estabelecimento" value={selectedEvent.establishment} className="col-span-2" />
              {selectedEvent.full_location_description && (
                <DetailTextBlock 
                  label="Descrição Completa" 
                  value={selectedEvent.full_location_description} 
                />
              )}
            </DetailSection>

            <DetailSection title="Geolocalização" icon={<Globe className="h-3.5 w-3.5" />}>
              <DetailField 
                label="Latitude" 
                value={selectedEvent.latitude?.toFixed(6)} 
                mono 
              />
              <DetailField 
                label="Longitude" 
                value={selectedEvent.longitude?.toFixed(6)} 
                mono 
              />
              <DetailField label="Plus Code" value={selectedEvent.plus_code} mono />
              <DetailField 
                label="Confiança" 
                value={
                  selectedEvent.geocoding_confidence !== null ? (
                    <span className="font-medium">
                      {(selectedEvent.geocoding_confidence * 100).toFixed(0)}%
                    </span>
                  ) : null
                } 
              />
              <DetailField 
                label="Endereço Formatado" 
                value={selectedEvent.formatted_address} 
                className="col-span-2" 
              />
              <DetailField label="Precisão" value={selectedEvent.location_precision} />
              <DetailField label="Fonte" value={selectedEvent.geocoding_source} />
              {selectedEvent.latitude && selectedEvent.longitude && (
                <div className="col-span-2 pt-2">
                  <a
                    href={`https://www.google.com/maps?q=${selectedEvent.latitude},${selectedEvent.longitude}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium rounded-md transition-colors"
                  >
                    <Navigation className="h-4 w-4" />
                    Abrir no Google Maps
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
            </DetailSection>

            <DetailSection title="Data e Hora" icon={<Calendar className="h-3.5 w-3.5" />}>
              <DetailField label="Data do Evento" value={formatDate(selectedEvent.event_date)} />
              <DetailField label="Precisão" value={selectedEvent.date_precision} />
              <DetailField label="Período do Dia" value={selectedEvent.time_of_day} />
            </DetailSection>

            <DetailSection title="Vítimas e Autores" icon={<Users className="h-3.5 w-3.5" />}>
              <DetailField 
                label="Total de Vítimas" 
                value={
                  selectedEvent.victim_count !== null ? (
                    <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                      {selectedEvent.victim_count}
                    </span>
                  ) : null
                } 
              />
              <DetailField label="Vítimas Identificadas" value={selectedEvent.identified_victim_count} />
              <DetailField 
                label="Total de Autores" 
                value={
                  selectedEvent.perpetrator_count !== null ? (
                    <span className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
                      {selectedEvent.perpetrator_count}
                    </span>
                  ) : null
                } 
              />
              <DetailField label="Autores Identificados" value={selectedEvent.identified_perpetrator_count} />
              {selectedEvent.victims_summary && (
                <DetailTextBlock label="Resumo das Vítimas" value={selectedEvent.victims_summary} />
              )}
            </DetailSection>

            <DetailSection title="Descrição" icon={<FileText className="h-3.5 w-3.5" />} columns={1}>
              <DetailTextBlock 
                label="Descrição Cronológica" 
                value={selectedEvent.chronological_description} 
              />
              {selectedEvent.additional_context && (
                <DetailTextBlock 
                  label="Contexto Adicional" 
                  value={selectedEvent.additional_context} 
                />
              )}
            </DetailSection>

            <DetailSection title="Metadados" icon={<Calendar className="h-3.5 w-3.5" />}>
              <DetailField label="Criado em" value={formatDateTime(selectedEvent.created_at)} />
              <DetailField label="Atualizado em" value={formatDateTime(selectedEvent.updated_at)} />
            </DetailSection>

            <DetailJson 
              label="Dados Mesclados" 
              data={selectedEvent.merged_data} 
            />
          </>
        )}
      </DetailSidebar>
    </div>
  );
}
