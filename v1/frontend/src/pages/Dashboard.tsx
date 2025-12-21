import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { fetchStats, type Stats } from '@/lib/api';
import { Loader2, Newspaper, FileText, CheckCircle, AlertCircle, Clock, Download } from 'lucide-react';

function StatCard({
  title,
  value,
  icon: Icon,
  description,
  variant = 'default',
}: {
  title: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
  description?: string;
  variant?: 'default' | 'success' | 'warning' | 'danger';
}) {
  const variantClasses = {
    default: 'text-foreground',
    success: 'text-emerald-600',
    warning: 'text-amber-600',
    danger: 'text-rose-600',
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className={`h-4 w-4 ${variantClasses[variant]}`} />
      </CardHeader>
      <CardContent>
        <div className={`text-2xl font-bold ${variantClasses[variant]}`}>{value.toLocaleString()}</div>
        {description && <p className="text-xs text-muted-foreground mt-1">{description}</p>}
      </CardContent>
    </Card>
  );
}

export function Dashboard() {
  const { data: stats, isLoading, error } = useQuery<Stats>({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 10000, // Refresh every 10 seconds
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p>Failed to load stats. Is the backend running?</p>
        <p className="text-sm mt-1">{(error as Error).message}</p>
      </div>
    );
  }

  if (!stats) return null;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">Overview of the violence archive pipeline</p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Sources"
          value={stats.sources.total}
          icon={Newspaper}
          description="Google News articles collected"
        />
        <StatCard
          title="Pending"
          value={stats.sources.pending}
          icon={Clock}
          variant="warning"
          description="Awaiting content download"
        />
        <StatCard
          title="Downloaded"
          value={stats.sources.downloaded}
          icon={Download}
          description="Ready for extraction"
        />
        <StatCard
          title="Processed"
          value={stats.sources.processed}
          icon={CheckCircle}
          variant="success"
          description="Extraction complete"
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        <StatCard
          title="Failed"
          value={stats.sources.failed}
          icon={AlertCircle}
          variant="danger"
          description="Sources with errors"
        />
        <StatCard
          title="Raw Events"
          value={stats.raw_events.total}
          icon={FileText}
          description="Extracted from sources"
        />
        <StatCard
          title="Unique Events"
          value={stats.unique_events.total}
          icon={CheckCircle}
          variant="success"
          description="Deduplicated events"
        />
      </div>
    </div>
  );
}

