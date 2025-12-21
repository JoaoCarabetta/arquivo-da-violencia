import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import {
  fetchPipelineStatus,
  triggerIngest,
  triggerDownload,
  triggerExtract,
  type Job,
  type PipelineStatus,
} from '@/lib/api';
import { Loader2, Play, RefreshCw, Inbox, Download, FileText, CheckCircle, XCircle } from 'lucide-react';

function formatTime(isoString: string | null) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function Jobs() {
  const queryClient = useQueryClient();
  const [lastTriggered, setLastTriggered] = useState<string | null>(null);

  const { data: status, isLoading, error, refetch } = useQuery({
    queryKey: ['pipeline-status'],
    queryFn: fetchPipelineStatus,
    refetchInterval: 3000, // Refresh every 3 seconds
  });

  const ingestMutation = useMutation({
    mutationFn: () => triggerIngest(),
    onSuccess: (data) => {
      setLastTriggered(`✓ Ingest job queued: ${data.job_id.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] });
    },
    onError: (err) => setLastTriggered(`✗ Error: ${(err as Error).message}`),
  });

  const downloadMutation = useMutation({
    mutationFn: () => triggerDownload(50),
    onSuccess: (data) => {
      setLastTriggered(`✓ Download job queued: ${data.job_id.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] });
    },
    onError: (err) => setLastTriggered(`✗ Error: ${(err as Error).message}`),
  });

  const extractMutation = useMutation({
    mutationFn: () => triggerExtract(10),
    onSuccess: (data) => {
      setLastTriggered(`✓ Extract job queued: ${data.job_id.slice(0, 8)}...`);
      queryClient.invalidateQueries({ queryKey: ['pipeline-status'] });
    },
    onError: (err) => setLastTriggered(`✗ Error: ${(err as Error).message}`),
  });

  const isAnyLoading = ingestMutation.isPending || downloadMutation.isPending || extractMutation.isPending;

  const isRedisConnected = status?.redis === 'connected';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Pipeline Jobs</h1>
        <p className="text-muted-foreground">Manage and monitor background pipeline jobs</p>
      </div>

      {/* Redis Status */}
      <div className="flex items-center gap-2 text-sm">
        {isRedisConnected ? (
          <>
            <CheckCircle className="h-4 w-4 text-green-500" />
            <span className="text-green-600">Redis connected</span>
            <span className="text-muted-foreground">• {status?.queued_jobs || 0} jobs in queue</span>
          </>
        ) : (
          <>
            <XCircle className="h-4 w-4 text-red-500" />
            <span className="text-red-600">Redis disconnected</span>
            <span className="text-muted-foreground">• Run: brew services start redis</span>
          </>
        )}
      </div>

      {/* Pipeline Actions */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Inbox className="h-5 w-5" />
              Ingest
            </CardTitle>
            <CardDescription>Fetch news from Google News RSS</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={() => ingestMutation.mutate()}
              disabled={isAnyLoading || !isRedisConnected}
              className="w-full"
            >
              {ingestMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Run Ingestion
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Download className="h-5 w-5" />
              Download
            </CardTitle>
            <CardDescription>Download article content</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={() => downloadMutation.mutate()}
              disabled={isAnyLoading || !isRedisConnected}
              className="w-full"
            >
              {downloadMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Run Download
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-lg">
              <FileText className="h-5 w-5" />
              Extract
            </CardTitle>
            <CardDescription>Extract events with LLM</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              onClick={() => extractMutation.mutate()}
              disabled={isAnyLoading || !isRedisConnected}
              className="w-full"
            >
              {extractMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
              ) : (
                <Play className="h-4 w-4 mr-2" />
              )}
              Run Extraction
            </Button>
          </CardContent>
        </Card>
      </div>

      {lastTriggered && (
        <div className={`text-sm px-4 py-2 rounded-md ${
          lastTriggered.startsWith('✓') 
            ? 'bg-green-50 text-green-700 border border-green-200' 
            : 'bg-red-50 text-red-700 border border-red-200'
        }`}>
          {lastTriggered}
        </div>
      )}

      {/* Queued Jobs */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Queued Jobs</span>
            <Button variant="outline" size="sm" onClick={() => refetch()}>
              <RefreshCw className="h-4 w-4 mr-2" />
              Refresh
            </Button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : error ? (
            <div className="text-center py-8 text-muted-foreground">
              <XCircle className="h-8 w-8 mx-auto mb-2 text-red-400" />
              Failed to load jobs
              <p className="text-sm mt-1">{(error as Error).message}</p>
            </div>
          ) : !status?.jobs?.length ? (
            <div className="text-center py-8 text-muted-foreground">
              <CheckCircle className="h-8 w-8 mx-auto mb-2 text-green-400" />
              No jobs in queue
              <p className="text-sm mt-1">Use the buttons above to trigger pipeline stages</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Job ID</TableHead>
                  <TableHead>Function</TableHead>
                  <TableHead>Enqueued At</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {status.jobs.map((job: Job) => (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-mono text-xs">{job.job_id.slice(0, 8)}...</TableCell>
                    <TableCell>
                      <Badge variant="outline">{job.function}</Badge>
                    </TableCell>
                    <TableCell className="text-sm">{formatTime(job.enqueue_time)}</TableCell>
                    <TableCell>
                      <Badge variant="secondary">Queued</Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
