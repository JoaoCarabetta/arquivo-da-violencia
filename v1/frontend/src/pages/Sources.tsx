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
import { fetchSources, type SourceGoogleNews } from '@/lib/api';
import { Loader2, ChevronLeft, ChevronRight, ExternalLink, Link2, Clock, Newspaper } from 'lucide-react';
import {
  DetailSidebar,
  DetailField,
  DetailSection,
  DetailLink,
  DetailContent,
} from '@/components/DetailSidebar';
import { SourcesPerHourChart } from '@/components/SourcesPerHourChart';

const statusConfig: Record<string, { variant: 'default' | 'secondary' | 'destructive' | 'outline'; label: string }> = {
  pending: { variant: 'secondary', label: 'Pendente' },
  downloaded: { variant: 'outline', label: 'Baixado' },
  processed: { variant: 'default', label: 'Processado' },
  failed: { variant: 'destructive', label: 'Falhou' },
  ignored: { variant: 'secondary', label: 'Ignorado' },
};

function formatDate(dateStr: string | null) {
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
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function Sources() {
  const [page, setPage] = useState(1);
  const [selectedSource, setSelectedSource] = useState<SourceGoogleNews | null>(null);
  const perPage = 20;

  const { data, isLoading, error } = useQuery({
    queryKey: ['sources', page, perPage],
    queryFn: () => fetchSources(page, perPage),
    placeholderData: (prev) => prev,
  });

  const statusInfo = selectedSource ? statusConfig[selectedSource.status] : null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Sources</h1>
        <p className="text-muted-foreground">Google News articles collected by the pipeline</p>
      </div>

      <SourcesPerHourChart />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>All Sources</span>
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
              Failed to load sources. Is the backend running?
            </div>
          ) : !data?.items.length ? (
            <div className="text-center py-8 text-muted-foreground">
              No sources found. Run the ingestion pipeline to collect news articles.
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[60px]">ID</TableHead>
                    <TableHead>Headline</TableHead>
                    <TableHead>Publisher</TableHead>
                    <TableHead>Published</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead className="w-[60px]">Link</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {data.items.map((source: SourceGoogleNews) => (
                    <TableRow
                      key={source.id}
                      className="cursor-pointer hover:bg-muted/50"
                      onClick={() => setSelectedSource(source)}
                    >
                      <TableCell className="font-mono text-xs">{source.id}</TableCell>
                      <TableCell className="max-w-[400px] truncate" title={source.headline || undefined}>
                        {source.headline || '—'}
                      </TableCell>
                      <TableCell>{source.publisher_name || '—'}</TableCell>
                      <TableCell className="text-sm">{formatShortDate(source.published_at)}</TableCell>
                      <TableCell>
                        <Badge variant={statusConfig[source.status]?.variant || 'secondary'}>
                          {statusConfig[source.status]?.label || source.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {source.resolved_url && (
                          <a
                            href={source.resolved_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-muted-foreground hover:text-foreground"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <ExternalLink className="h-4 w-4" />
                          </a>
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
        open={!!selectedSource}
        onOpenChange={(open) => !open && setSelectedSource(null)}
        title={`Source #${selectedSource?.id}`}
        subtitle={selectedSource?.headline || undefined}
        badge={
          statusInfo && (
            <Badge variant={statusInfo.variant} className="shrink-0">
              {statusInfo.label}
            </Badge>
          )
        }
      >
        {selectedSource && (
          <>
            <DetailSection title="Article Info" icon={<Newspaper className="h-3.5 w-3.5" />}>
              <DetailField label="ID" value={selectedSource.id} mono />
              <DetailField label="Publisher" value={selectedSource.publisher_name} />
              <DetailField label="Search Query" value={selectedSource.search_query} className="col-span-2" />
            </DetailSection>

            <DetailSection title="URLs" icon={<Link2 className="h-3.5 w-3.5" />} columns={1}>
              <DetailLink label="Google News URL" url={selectedSource.google_news_url} />
              <DetailLink label="Resolved URL" url={selectedSource.resolved_url} />
            </DetailSection>

            <DetailSection title="Timestamps" icon={<Clock className="h-3.5 w-3.5" />}>
              <DetailField label="Published" value={formatDate(selectedSource.published_at)} />
              <DetailField label="Fetched" value={formatDate(selectedSource.fetched_at)} />
              <DetailField label="Updated" value={formatDate(selectedSource.updated_at)} className="col-span-2" />
            </DetailSection>

            <DetailContent
              label="Extracted Content"
              content={selectedSource.content}
              maxHeight="350px"
            />
          </>
        )}
      </DetailSidebar>
    </div>
  );
}
