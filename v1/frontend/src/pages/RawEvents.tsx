import { useState, useEffect } from 'react';
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
import { fetchRawEvents, fetchSourceById, type RawEvent, type SourceGoogleNews } from '@/lib/api';
import { 
  Loader2, ChevronLeft, ChevronRight, Check, X, 
  Crosshair, MapPin, Calendar, Users, FileText, Settings, Shield, Newspaper
} from 'lucide-react';
import {
  DetailSidebar,
  DetailField,
  DetailSection,
  DetailTextBlock,
  DetailJson,
  DetailContent,
  DetailLink,
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

export function RawEvents() {
  const [page, setPage] = useState(1);
  const [selectedEvent, setSelectedEvent] = useState<RawEvent | null>(null);
  const [sourceContent, setSourceContent] = useState<SourceGoogleNews | null>(null);
  const perPage = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ['raw-events', page, perPage],
    queryFn: () => fetchRawEvents(page, perPage),
    placeholderData: (prev) => prev,
  });

  // Fetch source content when a raw event with source_google_news_id is selected
  useEffect(() => {
    if (selectedEvent?.source_google_news_id) {
      fetchSourceById(selectedEvent.source_google_news_id)
        .then(setSourceContent)
        .catch(() => setSourceContent(null));
    } else {
      setSourceContent(null);
    }
  }, [selectedEvent?.source_google_news_id]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Raw Events</h1>
        <p className="text-muted-foreground">Events extracted from news articles by the LLM</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>All Raw Events</span>
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
              Failed to load raw events. Is the backend running?
            </div>
          ) : !data?.items.length ? (
            <div className="text-center py-8 text-muted-foreground">
              No raw events found. Run the extraction pipeline to process sources.
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
                    <TableHead className="text-center">Security</TableHead>
                    <TableHead className="text-center">OK</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((event: RawEvent) => (
                    <TableRow
                      key={event.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setSelectedEvent(event)}
                    >
                      <TableCell className="font-mono text-xs">{event.id}</TableCell>
                      <TableCell className="max-w-[300px] truncate" title={event.title || undefined}>
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
                      <TableCell className="text-sm max-w-[200px] truncate">
                        {[event.neighborhood, event.city].filter(Boolean).join(', ') || '—'}
                      </TableCell>
                      <TableCell className="text-sm">{formatShortDate(event.event_date)}</TableCell>
                      <TableCell className="text-center font-medium">{event.victim_count ?? '—'}</TableCell>
                      <TableCell className="text-center">
                        {event.security_force_involved === true && (
                          <Badge variant="destructive" className="text-xs">Sim</Badge>
                        )}
                        {event.security_force_involved === false && (
                          <span className="text-muted-foreground text-xs">Não</span>
                        )}
                        {event.security_force_involved === null && '—'}
                      </TableCell>
                      <TableCell className="text-center">
                        {event.extraction_success ? (
                          <Check className="h-4 w-4 text-emerald-600 mx-auto" />
                        ) : (
                          <X className="h-4 w-4 text-rose-600 mx-auto" />
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
        title={`Raw Event #${selectedEvent?.id}`}
        subtitle={selectedEvent?.title || undefined}
        width="wide"
        badge={
          selectedEvent && (
            <Badge 
              variant={selectedEvent.extraction_success ? 'default' : 'destructive'}
              className="shrink-0"
            >
              {selectedEvent.extraction_success ? 'Extraído' : 'Falhou'}
            </Badge>
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
              <DetailField label="Estado" value={selectedEvent.state} />
              <DetailField label="Cidade" value={selectedEvent.city} />
              <DetailField label="Bairro" value={selectedEvent.neighborhood} className="col-span-2" />
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
            </DetailSection>

            {/* Comparison: Extracted Data vs Source Content - Side by Side */}
            {sourceContent && (
              <div className="bg-white dark:bg-zinc-900 rounded-lg border border-zinc-200 dark:border-zinc-800 overflow-hidden">
                <div className="px-3 py-2 bg-zinc-100/50 dark:bg-zinc-800/50 border-b border-zinc-200 dark:border-zinc-800">
                  <h4 className="text-[10px] font-semibold uppercase tracking-wider text-zinc-500 dark:text-zinc-400 flex items-center gap-1.5">
                    <FileText className="h-3.5 w-3.5" />
                    Comparação: Extração vs Conteúdo Original
                  </h4>
                </div>
                <div className="grid grid-cols-2 divide-x divide-zinc-200 dark:divide-zinc-800 min-h-[600px]">
                  {/* Left: Extracted Data */}
                  <div className="p-3 space-y-3 min-h-0 flex flex-col overflow-hidden">
                    <div className="flex-1 min-h-0 flex flex-col">
                      <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-1.5 shrink-0">
                        Dados Extraídos
                      </dt>
                      {selectedEvent.chronological_description && (
                        <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-md p-2.5 border border-zinc-100 dark:border-zinc-800 overflow-auto flex-1 min-h-0">
                          <p className="text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
                            {selectedEvent.chronological_description}
                          </p>
                        </div>
                      )}
                    </div>
                    <div className="grid grid-cols-1 gap-2 shrink-0">
                      <DetailField label="Título" value={selectedEvent.title} />
                      <DetailField label="Tipo" value={selectedEvent.homicide_type} />
                      <DetailField label="Vítimas" value={selectedEvent.victim_count} />
                      <DetailField label="Local" value={[selectedEvent.neighborhood, selectedEvent.city].filter(Boolean).join(', ') || selectedEvent.city} />
                      <DetailField label="Data" value={formatDate(selectedEvent.event_date)} />
                    </div>
                  </div>
                  
                  {/* Right: Source Content */}
                  <div className="p-3 space-y-3 min-h-0 flex flex-col overflow-hidden">
                    <div className="flex-1 min-h-0 flex flex-col">
                      <dt className="text-[10px] font-medium text-zinc-400 dark:text-zinc-500 uppercase tracking-wide mb-1.5 shrink-0">
                        Conteúdo Original
                      </dt>
                      <div className="bg-zinc-50 dark:bg-zinc-800/50 rounded-md p-2.5 border border-zinc-100 dark:border-zinc-800 overflow-auto flex-1 min-h-0">
                        <p className="text-xs text-zinc-700 dark:text-zinc-300 leading-relaxed whitespace-pre-wrap">
                          {sourceContent.content}
                        </p>
                      </div>
                    </div>
                    <div className="space-y-2 shrink-0">
                      <DetailLink label="Link do Artigo" url={sourceContent.resolved_url || sourceContent.google_news_url} />
                      <DetailField label="Publicado em" value={formatDateTime(sourceContent.published_at)} />
                      <DetailField label="Editora" value={sourceContent.publisher_name} />
                    </div>
                  </div>
                </div>
              </div>
            )}

            {!sourceContent && (
              <DetailSection title="Descrição" icon={<FileText className="h-3.5 w-3.5" />} columns={1}>
                <DetailTextBlock 
                  label="Descrição Cronológica" 
                  value={selectedEvent.chronological_description} 
                />
              </DetailSection>
            )}

            <DetailSection title="Metadados de Extração" icon={<Settings className="h-3.5 w-3.5" />}>
              <DetailField label="Modelo LLM" value={selectedEvent.extraction_model} mono />
              <DetailField label="Source ID" value={selectedEvent.source_google_news_id} mono />
              <DetailField label="Unique Event ID" value={selectedEvent.unique_event_id} mono />
              <DetailField label="Criado em" value={formatDateTime(selectedEvent.created_at)} />
              {selectedEvent.extraction_error && (
                <div className="col-span-2 bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 rounded-md p-2.5">
                  <p className="text-[10px] font-medium text-rose-600 dark:text-rose-400 uppercase tracking-wide mb-1">
                    Erro de Extração
                  </p>
                  <p className="text-xs text-rose-700 dark:text-rose-300">
                    {selectedEvent.extraction_error}
                  </p>
                </div>
              )}
            </DetailSection>

            <DetailJson 
              label="Dados Completos da Extração" 
              data={selectedEvent.extraction_data} 
            />
          </>
        )}
      </DetailSidebar>
    </div>
  );
}
