"use client"

import { Bar, BarChart, CartesianGrid, XAxis, Legend } from "recharts"
import { useQuery } from "@tanstack/react-query"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  type ChartConfig,
} from "@/components/ui/chart"
import { fetchSourcesByHour } from "@/lib/api"
import { Loader2 } from "lucide-react"

// Status labels and colors
const statusLabels: Record<string, string> = {
  ready_for_classification: "Aguardando Classificação",
  discarded: "Descartado",
  ready_for_download: "Aguardando Download",
  failed_in_download: "Falhou no Download",
  ready_for_extraction: "Aguardando Extração",
  failed_in_extraction: "Falhou na Extração",
  extracted: "Extraído",
}

const statusColors: Record<string, string> = {
  ready_for_classification: "var(--color-chart-1)", // blue
  discarded: "var(--color-chart-2)", // gray
  ready_for_download: "var(--color-chart-3)", // yellow
  failed_in_download: "var(--color-chart-4)", // red
  ready_for_extraction: "var(--color-chart-5)", // orange
  failed_in_extraction: "hsl(var(--destructive))", // destructive red
  extracted: "var(--color-chart-6)", // green
}

const statusOrder = [
  "extracted",
  "ready_for_extraction",
  "failed_in_extraction",
  "ready_for_download",
  "failed_in_download",
  "ready_for_classification",
  "discarded",
]

const chartConfig: ChartConfig = statusOrder.reduce((config, status) => {
  config[status] = {
    label: statusLabels[status],
    color: statusColors[status],
  }
  return config
}, {} as ChartConfig)

// Custom tooltip component
function CustomTooltip({ active, payload }: any) {
  if (!active || !payload || !payload.length) {
    return null
  }

  // Get the date from the first payload item
  const data = payload[0].payload
  const fullHour = data.fullHour
  const date = new Date(fullHour.replace(' ', 'T') + 'Z')
  const formattedDate = date.toLocaleString('pt-BR', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'America/Sao_Paulo',
  })

  // Filter to only show non-zero values
  const nonZeroItems = payload.filter((item: any) => item.value > 0)

  if (nonZeroItems.length === 0) {
    return null
  }

  return (
    <div className="rounded-lg border bg-background p-2 shadow-sm">
      <div className="mb-1 text-xs font-medium">{formattedDate}</div>
      <div className="grid gap-1">
        {nonZeroItems.map((item: any) => (
          <div key={item.dataKey} className="flex items-center gap-2 text-xs">
            <div 
              className="h-2.5 w-2.5 rounded-sm" 
              style={{ backgroundColor: item.color }}
            />
            <span className="flex-1">{item.name}</span>
            <span className="font-medium">{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export function SourcesPerHourChart() {
  const hours = 48
  const { data, isLoading, error } = useQuery({
    queryKey: ['sources-by-hour', hours],
    queryFn: () => fetchSourcesByHour(hours),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sources Fetched Per Hour</CardTitle>
          <CardDescription>Last {hours} hours</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[250px]">
            <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          </div>
        </CardContent>
      </Card>
    )
  }

  if (error || !data?.data.length) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sources Fetched Per Hour</CardTitle>
          <CardDescription>Last {hours} hours</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-center h-[250px] text-muted-foreground">
            {error ? "Failed to load chart data" : "No data available"}
          </div>
        </CardContent>
      </Card>
    )
  }

  // Format the data for the chart
  const chartData = data.data.map((item) => {
    // Parse UTC datetime from SQLite format (YYYY-MM-DD HH:MM:SS)
    const date = new Date(item.hour.replace(' ', 'T') + 'Z')
    return {
      hour: date.toLocaleString('pt-BR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        timeZone: 'America/Sao_Paulo',
      }),
      hourOnly: date.toLocaleString('pt-BR', {
        hour: '2-digit',
        timeZone: 'America/Sao_Paulo',
      }) + 'h',
      day: date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'short',
        timeZone: 'America/Sao_Paulo',
      }),
      fullHour: item.hour,
      count: item.count,
      // Include all status counts
      ...statusOrder.reduce((acc, status) => {
        const statusValue = item[status as keyof typeof item]
        acc[status] = typeof statusValue === 'number' ? statusValue : 0
        return acc
      }, {} as Record<string, number>),
    }
  })

  const total = chartData.reduce((acc, curr) => acc + curr.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources Fetched Per Hour</CardTitle>
        <CardDescription>
          Showing {total.toLocaleString()} total sources for the last {hours} hours
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
          <BarChart
            accessibilityLayer
            data={chartData}
            margin={{
              left: 12,
              right: 12,
              bottom: 60,
            }}
          >
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="hourOnly"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              angle={-45}
              textAnchor="end"
              height={60}
            />
            <ChartTooltip content={<CustomTooltip />} cursor={false} />
            <Legend 
              wrapperStyle={{ paddingTop: '20px' }}
              formatter={(value) => statusLabels[value] || value}
            />
            {statusOrder.map((status) => (
              <Bar
                key={status}
                dataKey={status}
                stackId="sources"
                fill={statusColors[status]}
                radius={status === 'extracted' ? [4, 4, 0, 0] : undefined}
              />
            ))}
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

