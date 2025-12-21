import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { fetchPublicEvents, type PublicEvent } from '@/lib/api';
import { Loader2, ChevronLeft, ChevronRight, MapPin, Users, Clock, Shield, Search, ExternalLink } from 'lucide-react';

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

function EventCard({ event, expanded, onToggle }: { event: PublicEvent; expanded: boolean; onToggle: () => void }) {
  return (
    <Card className="hover:shadow-md transition-shadow cursor-pointer" onClick={onToggle}>
      <CardContent className="pt-6">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Clock className="h-4 w-4" />
            {formatRelativeTime(event.created_at)}
          </div>
          <div className="flex gap-2">
            {event.homicide_type && (
              <Badge variant="outline">{event.homicide_type}</Badge>
            )}
            {event.security_force_involved && (
              <Badge variant="destructive" className="gap-1">
                <Shield className="h-3 w-3" />
                Forças de Segurança
              </Badge>
            )}
          </div>
        </div>

        <h3 className="text-lg font-semibold mb-2">
          {event.title || 'Sem título'}
        </h3>

        <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground mb-3">
          {event.city && event.state && (
            <div className="flex items-center gap-1">
              <MapPin className="h-4 w-4" />
              {event.neighborhood && `${event.neighborhood}, `}
              {event.city}, {event.state}
            </div>
          )}
          {event.victim_count && (
            <div className="flex items-center gap-1">
              <Users className="h-4 w-4" />
              {event.victim_count} {event.victim_count === 1 ? 'vítima' : 'vítimas'}
            </div>
          )}
          {event.method_of_death && (
            <div>
              {event.method_of_death}
            </div>
          )}
          <div className="text-xs">
            {event.source_count} {event.source_count === 1 ? 'fonte' : 'fontes'}
          </div>
        </div>

        {expanded && event.chronological_description && (
          <div className="mt-4 pt-4 border-t">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">
              {event.chronological_description}
            </p>
            {event.latitude && event.longitude && (
              <div className="mt-4">
                <a
                  href={`https://www.google.com/maps?q=${event.latitude},${event.longitude}`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 text-sm text-primary hover:underline"
                  onClick={(e) => e.stopPropagation()}
                >
                  <MapPin className="h-4 w-4" />
                  Ver no Google Maps
                  <ExternalLink className="h-3 w-3" />
                </a>
              </div>
            )}
          </div>
        )}

        {!expanded && event.chronological_description && (
          <p className="text-sm text-muted-foreground line-clamp-2">
            {event.chronological_description}
          </p>
        )}
      </CardContent>
    </Card>
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
          <div className="space-y-4 mb-6">
            {data.items.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                expanded={expandedId === event.id}
                onToggle={() => setExpandedId(expandedId === event.id ? null : event.id)}
              />
            ))}
          </div>

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

