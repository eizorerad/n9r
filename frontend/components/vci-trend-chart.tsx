'use client'

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'
import { cn } from '@/lib/utils'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'

interface DataPoint {
  date: string
  vci_score: number
  grade: string
  commit_sha: string | null
}

interface VCITrendChartProps {
  data: DataPoint[]
  className?: string
}

export function VCITrendChart({ data, className }: VCITrendChartProps) {
  if (!data || data.length === 0) {
    return (
      <Card className={cn('border-border/50 glass-panel flex flex-col', className)}>
        <CardHeader>
          <CardTitle className="text-sm font-medium text-muted-foreground">VCI Trend</CardTitle>
        </CardHeader>
        <CardContent className="flex-1 flex items-center justify-center text-muted-foreground/50">
          No analysis history yet
        </CardContent>
      </Card>
    )
  }

  const formattedData = data.map(d => ({
    ...d,
    date: new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
  }))

  const minScore = Math.min(...data.map(d => d.vci_score))
  const maxScore = Math.max(...data.map(d => d.vci_score))
  const yMin = Math.max(0, minScore - 10)
  const yMax = Math.min(100, maxScore + 10)

  return (
    <Card className={cn('border-border/50 glass-panel', className)}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">VCI Trend</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={formattedData}>
              <defs>
                <linearGradient id="vciGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#10b981" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#10b981" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                stroke="#71717a"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                dy={10}
              />
              <YAxis
                domain={[yMin, yMax]}
                stroke="#71717a"
                fontSize={11}
                tickLine={false}
                axisLine={false}
                tickFormatter={(value) => `${value}`}
                dx={-10}
              />
              <Tooltip
                contentStyle={{
                  backgroundColor: '#18181b',
                  border: '1px solid #27272a',
                  borderRadius: '8px',
                  fontSize: '12px',
                  boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)',
                }}
                labelStyle={{ color: '#a1a1aa' }}
                itemStyle={{ color: '#10b981' }}
                content={({ active, payload, label }) => {
                  if (!active || !payload || payload.length === 0) return null
                  const dataPoint = payload[0].payload as DataPoint
                  return (
                    <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-2 shadow-lg">
                      <p className="text-zinc-400 text-xs mb-1">{label}</p>
                      <p className="text-emerald-400 font-medium">VCI Score: {dataPoint.vci_score}</p>
                      {dataPoint.commit_sha && (
                        <p className="text-zinc-500 text-xs mt-1 font-mono">
                          Commit: {dataPoint.commit_sha}
                        </p>
                      )}
                    </div>
                  )
                }}
              />
              <Area
                type="monotone"
                dataKey="vci_score"
                stroke="#10b981"
                strokeWidth={2}
                fill="url(#vciGradient)"
                dot={{ fill: '#10b981', strokeWidth: 0, r: 4 }}
                activeDot={{ fill: '#10b981', strokeWidth: 2, stroke: '#fff', r: 6 }}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  )
}
