"use client"

import * as React from "react"
import { Bar, BarChart, CartesianGrid, XAxis } from "recharts"
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
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import { fetchSourcesByHour, type SourcesByHour } from "@/lib/api"
import { Loader2 } from "lucide-react"

const chartConfig = {
  count: {
    label: "Sources",
    color: "var(--color-chart-1)",
  },
} satisfies ChartConfig

export function SourcesPerHourChart() {
  const { data, isLoading, error } = useQuery({
    queryKey: ['sources-by-hour', 24],
    queryFn: () => fetchSourcesByHour(24),
  })

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Sources Fetched Per Hour</CardTitle>
          <CardDescription>Last 24 hours</CardDescription>
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
          <CardDescription>Last 24 hours</CardDescription>
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
    const date = new Date(item.hour)
    return {
      hour: date.toLocaleString('pt-BR', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
      }),
      hourOnly: date.toLocaleString('pt-BR', {
        hour: '2-digit',
      }) + 'h',
      day: date.toLocaleDateString('pt-BR', {
        day: '2-digit',
        month: 'short',
      }),
      fullHour: item.hour,
      count: item.count,
    }
  })

  const total = chartData.reduce((acc, curr) => acc + curr.count, 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sources Fetched Per Hour</CardTitle>
        <CardDescription>
          Showing {total.toLocaleString()} total sources for the last 24 hours
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
            <ChartTooltip
              content={
                <ChartTooltipContent
                  className="w-[150px]"
                  labelFormatter={(value, payload) => {
                    if (payload && payload[0]) {
                      const fullHour = (payload[0].payload as typeof chartData[0]).fullHour
                      return new Date(fullHour).toLocaleString('pt-BR', {
                        month: 'short',
                        day: 'numeric',
                        year: 'numeric',
                        hour: '2-digit',
                        minute: '2-digit',
                      })
                    }
                    return value
                  }}
                />
              }
            />
            <Bar dataKey="count" fill={chartConfig.count.color} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}

