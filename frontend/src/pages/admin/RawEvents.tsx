import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
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
import { fetchRawEvents, type RawEvent } from '@/lib/api';
import { 
  Loader2, ChevronLeft, ChevronRight
} from 'lucide-react';

function formatShortDate(dateStr: string | null) {
  if (!dateStr) return '—';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    timeZone: 'America/Sao_Paulo',
  });
}

export function RawEvents() {
  const [page, setPage] = useState(1);
  const navigate = useNavigate();
  const perPage = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ['raw-events', page, perPage],
    queryFn: () => fetchRawEvents(page, perPage),
    placeholderData: (prev) => prev,
  });

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
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((event: RawEvent) => (
                    <TableRow
                      key={event.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => navigate(`/admin/raw-events/${event.id}`)}
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
    </div>
  );
}
