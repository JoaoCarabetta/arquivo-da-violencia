import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import {
  fetchPublicStats,
  fetchStatsByType,
  fetchStatsByState,
  fetchStatsByDay,
  fetchPublicEvents,
} from '@/lib/api';
import { Loader2, TrendingUp, Users, Shield, MapPin, Clock } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Bar, BarChart, XAxis, CartesianGrid, LabelList } from 'recharts';
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from '@/components/ui/chart';
import { generateSEOTags, generateOrganizationSchema, generateWebSiteSchema } from '@/lib/seo';

function StatCard({
  title,
  value,
  icon: Icon,
}: {
  title: string;
  value: number;
  icon: React.ComponentType<{ className?: string }>;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-3xl font-bold">{value.toLocaleString()}</div>
      </CardContent>
    </Card>
  );
}

export function Home() {
  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['public-stats'],
    queryFn: fetchPublicStats,
    refetchInterval: 30000, // Refresh every 30s
    refetchOnWindowFocus: true,
  });

  // Manually trigger refetch every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      refetchStats();
    }, 30000);

    return () => clearInterval(interval);
  }, [refetchStats]);

  const { data: typeStats } = useQuery({
    queryKey: ['stats-by-type'],
    queryFn: fetchStatsByType,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });

  const { data: stateStats } = useQuery({
    queryKey: ['stats-by-state'],
    queryFn: fetchStatsByState,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });

  const { data: dayStats } = useQuery({
    queryKey: ['stats-by-day'],
    queryFn: () => fetchStatsByDay(30),
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });

  const { data: recentEvents } = useQuery({
    queryKey: ['recent-events'],
    queryFn: () => fetchPublicEvents(1, 5),
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
  });

  if (statsLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const topStates = stateStats?.slice(0, 5) || [];

  const chartConfig = {
    count: {
      label: "Mortes",
      color: "hsl(0, 100%, 50%)",
    },
  } satisfies ChartConfig;

  const seoTags = generateSEOTags({
    title: 'Monitoramento em tempo real de mortes violentas no Brasil',
    description: 'Dados abertos sobre mortes violentas no Brasil em tempo real. Acesse estatísticas, linha do tempo de eventos e baixe dados para pesquisa, jornalismo e sociedade civil.',
    path: '/',
  });

  const organizationSchema = generateOrganizationSchema();
  const websiteSchema = generateWebSiteSchema();

  return (
    <div className="space-y-12 py-12">
      {/* Main Counter */}
      <section className="container mx-auto px-6 text-center">
        <div className="relative bg-gradient-to-br from-rose-50 to-rose-100 dark:from-rose-950/30 dark:to-rose-900/20 rounded-2xl p-12">
          {/* LIVE indicator - top right corner */}
          <div className="absolute top-4 right-4">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-rose-600 opacity-75 animate-ping" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-rose-600" />
            </span>
          </div>

          <h1 className="text-center leading-tight">
            <span className="text-6xl md:text-7xl lg:text-8xl font-bold text-rose-600">
              {stats?.last_7_days?.toLocaleString?.() ?? 0}
            </span>
            <span className="block mt-3 text-3xl md:text-4xl lg:text-5xl font-bold text-rose-700 dark:text-rose-500">
              mortes violentas registradas nos últimos 7 dias no Brasil
            </span>
          </h1>

          {/* Short subtitle */}
          <p className="mt-4 text-base md:text-lg text-muted-foreground max-w-2xl mx-auto">
            Mortes violentas são evitáveis. Acesse os dados e ajude a evitá-las.
          </p>
        </div>
      </section>

      {/* Stats Cards */}
      <section className="container mx-auto px-6">
        <div className="grid gap-4 md:grid-cols-3">
          <StatCard title="Últimos 7 dias" value={stats?.last_7_days || 0} icon={TrendingUp} />
          <StatCard title="Últimos 30 dias" value={stats?.last_30_days || 0} icon={Users} />
          <StatCard title="Total" value={stats?.total || 0} icon={Shield} />
        </div>
      </section>

      {/* Death Types Breakdown */}
      <section className="container mx-auto px-6">
        <Card>
          <CardHeader>
            <CardTitle>Por Tipo de Morte</CardTitle>
          </CardHeader>
          <CardContent>
            {typeStats && typeStats.length > 0 ? (
              <div className="space-y-4">
                {typeStats.map((stat) => (
                  <div key={stat.type} className="flex items-center gap-4">
                    <div className="flex-1">
                      <div className="flex items-center justify-between mb-1">
                        <span className="text-sm font-medium">{stat.type}</span>
                        <span className="text-sm text-muted-foreground">
                          {stat.count.toLocaleString()} ({stat.percent}%)
                        </span>
                      </div>
                      <div className="h-2 bg-muted rounded-full overflow-hidden">
                        <div
                          className="h-full bg-rose-600 transition-all"
                          style={{ width: `${stat.percent}%` }}
                        />
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                Nenhum dado disponível
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Charts */}
      <section className="container mx-auto px-6">
        <div className="grid gap-6 md:grid-cols-2">
          {/* Daily Deaths Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Mortes por Dia (Últimos 30 dias)</CardTitle>
            </CardHeader>
            <CardContent>
              {dayStats && dayStats.length > 0 ? (
                <ChartContainer config={chartConfig}>
                  <BarChart
                    accessibilityLayer
                    data={dayStats}
                    margin={{
                      top: 20,
                    }}
                  >
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="date"
                      tickLine={false}
                      tickMargin={10}
                      axisLine={false}
                      tickFormatter={(value) => new Date(value).toLocaleDateString('pt-BR', { day: '2-digit', month: 'short' })}
                      fontSize={12}
                    />
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent hideLabel />}
                    />
                    <Bar dataKey="count" fill="#e11d48" radius={8}>
                      <LabelList
                        position="top"
                        offset={12}
                        className="fill-foreground"
                        fontSize={12}
                      />
                    </Bar>
                  </BarChart>
                </ChartContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </CardContent>
          </Card>

          {/* By State Chart */}
          <Card>
            <CardHeader>
              <CardTitle>Por Estado (Top 5)</CardTitle>
            </CardHeader>
            <CardContent>
              {topStates.length > 0 ? (
                <ChartContainer config={chartConfig}>
                  <BarChart
                    accessibilityLayer
                    data={topStates}
                    margin={{
                      top: 20,
                    }}
                  >
                    <CartesianGrid vertical={false} />
                    <XAxis
                      dataKey="state"
                      tickLine={false}
                      tickMargin={10}
                      axisLine={false}
                      fontSize={12}
                    />
                    <ChartTooltip
                      cursor={false}
                      content={<ChartTooltipContent hideLabel />}
                    />
                    <Bar dataKey="count" fill="#e11d48" radius={8}>
                      <LabelList
                        position="top"
                        offset={12}
                        className="fill-foreground"
                        fontSize={12}
                      />
                    </Bar>
                  </BarChart>
                </ChartContainer>
              ) : (
                <div className="h-[250px] flex items-center justify-center text-muted-foreground">
                  Nenhum dado disponível
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </section>

      {/* Recent Events */}
      <section className="container mx-auto px-6">
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Últimos Registros</CardTitle>
              <Link to="/eventos" className="text-sm text-primary hover:underline">
                Ver todos →
              </Link>
            </div>
          </CardHeader>
          <CardContent>
            {recentEvents && recentEvents.items.length > 0 ? (
              <div className="space-y-4">
                {recentEvents.items.map((event) => (
                  <div key={event.id} className="border rounded-lg p-4 hover:bg-muted/50 transition-colors">
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Clock className="h-4 w-4 text-muted-foreground" />
                        <span className="text-sm text-muted-foreground">
                          {event.event_date 
                            ? new Date(event.event_date).toLocaleDateString('pt-BR', {
                                day: '2-digit',
                                month: 'short',
                                year: 'numeric',
                              })
                            : 'Data não disponível'}
                        </span>
                      </div>
                      {event.homicide_type && (
                        <Badge variant="outline">{event.homicide_type}</Badge>
                      )}
                    </div>
                    <h3 className="font-medium mb-2">{event.title || 'Sem título'}</h3>
                    <div className="flex items-center gap-4 text-sm text-muted-foreground">
                      {event.city && event.state && (
                        <div className="flex items-center gap-1">
                          <MapPin className="h-3 w-3" />
                          {event.city}, {event.state}
                        </div>
                      )}
                      {event.victim_count && (
                        <div className="flex items-center gap-1">
                          <Users className="h-3 w-3" />
                          {event.victim_count} {event.victim_count === 1 ? 'vítima' : 'vítimas'}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-center py-8 text-muted-foreground">
                Nenhum evento registrado ainda
              </div>
            )}
          </CardContent>
        </Card>
      </section>

      {/* Call to Action */}
      <section className="container mx-auto px-6 text-center">
        <Card className="bg-gradient-to-br from-primary/5 to-primary/10 border-primary/20">
          <CardContent className="pt-6">
            <h2 className="text-2xl font-bold mb-4">Acesse os Dados Abertos</h2>
            <p className="text-muted-foreground mb-6 max-w-2xl mx-auto">
              Todos os dados estão disponíveis para download em formato CSV ou JSON. 
              Use para pesquisa, jornalismo ou análise.
            </p>
            <div className="flex gap-4 justify-center">
              <Link to="/dados">
                <button className="px-6 py-3 bg-primary text-primary-foreground rounded-lg font-medium hover:bg-primary/90 transition-colors">
                  Baixar Dados
                </button>
              </Link>
              <Link to="/sobre">
                <button className="px-6 py-3 border border-border rounded-lg font-medium hover:bg-muted transition-colors">
                  Entenda a Metodologia
                </button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </section>
    </div>
  );
}

