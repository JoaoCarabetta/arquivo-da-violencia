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
import {
  fetchPipelineStatus,
  type Job,
} from '@/lib/api';
import { Loader2, RefreshCw, CheckCircle, XCircle, AlertTriangle } from 'lucide-react';

function formatTime(isoString: string | null) {
  if (!isoString) return '—';
  return new Date(isoString).toLocaleTimeString('pt-BR', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  });
}

export function Jobs() {
  const { data: status, isLoading, error, refetch } = useQuery({
    queryKey: ['pipeline-status'],
    queryFn: fetchPipelineStatus,
    refetchInterval: 3000, // Refresh every 3 seconds
  });

  const isRedisConnected = status?.redis === 'connected';
  const isWorkerAlive = status?.worker_alive === true;
  const isCronEnabled = status?.cron_enabled === true;

  // Redis being up tells us nothing about whether the pipeline is actually
  // running. The worker (which also schedules cron) can be dead or have cron
  // disabled while Redis stays connected, which silently stalls everything.
  const isStalled = isRedisConnected && (!isWorkerAlive || !isCronEnabled);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Pipeline Jobs</h1>
        <p className="text-muted-foreground">Manage and monitor background pipeline jobs</p>
        <p className="text-sm text-green-600 mt-2">✓ Auto-reload is active - changes appear instantly!</p>
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

      {/* Worker / Cron Status */}
      {isRedisConnected && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          {isWorkerAlive ? (
            <span className="inline-flex items-center gap-1.5 text-green-600">
              <CheckCircle className="h-4 w-4 text-green-500" />
              Worker running
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-red-600">
              <XCircle className="h-4 w-4 text-red-500" />
              Worker not responding
            </span>
          )}
          <span className="text-muted-foreground">•</span>
          {isCronEnabled ? (
            <span className="inline-flex items-center gap-1.5 text-green-600">
              <CheckCircle className="h-4 w-4 text-green-500" />
              Hourly cron enabled
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 text-amber-600">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Cron disabled
            </span>
          )}
        </div>
      )}

      {/* Stalled pipeline warning - Redis up but nothing will run */}
      {isStalled && (
        <div className="flex items-start gap-3 rounded-md border border-amber-300 bg-amber-50 p-4 text-sm text-amber-800">
          <AlertTriangle className="h-5 w-5 flex-shrink-0 text-amber-500" />
          <div className="space-y-1">
            <p className="font-medium">Pipeline is stalled — nothing will be downloaded or classified.</p>
            {!isWorkerAlive && (
              <p>
                Redis is reachable but the <span className="font-mono">worker</span> process is not
                sending heartbeats. Check it on the server:{' '}
                <span className="font-mono">docker compose -p prod ps</span> and{' '}
                <span className="font-mono">docker compose -p prod logs --tail=200 worker</span>.
              </p>
            )}
            {isWorkerAlive && !isCronEnabled && (
              <p>
                The worker is running but scheduled ingestion is off. Set{' '}
                <span className="font-mono">ENABLE_CRON=true</span> in the server{' '}
                <span className="font-mono">.env</span> and restart the worker, or trigger a run
                manually from the API.
              </p>
            )}
          </div>
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
