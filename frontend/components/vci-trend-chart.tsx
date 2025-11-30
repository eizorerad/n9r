'use client'

import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, Area, AreaChart } from 'recharts'
import { cn } from '@/lib/utils'

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
      <div className={cn('rounded-xl border border-gray-800 bg-gray-900/50 p-6', className)}>
        <h3 className="text-sm font-medium text-gray-400 mb-4">VCI Trend</h3>
        <div className="h-48 flex items-center justify-center text-gray-500">
          No analysis history yet
        </div>
      </div>
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
    <div className={cn('rounded-xl border border-gray-800 bg-gray-900/50 p-6', className)}>
      <h3 className="text-sm font-medium text-gray-400 mb-4">VCI Trend</h3>
      <div className="h-48">
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
              stroke="#4b5563"
              fontSize={11}
              tickLine={false}
              axisLine={false}
            />
            <YAxis 
              domain={[yMin, yMax]}
              stroke="#4b5563"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={(value) => `${value}`}
            />
            <Tooltip 
              contentStyle={{
                backgroundColor: '#1f2937',
                border: '1px solid #374151',
                borderRadius: '8px',
                fontSize: '12px',
              }}
              labelStyle={{ color: '#9ca3af' }}
              itemStyle={{ color: '#10b981' }}
              formatter={(value: number, name: string) => [`${value}`, 'VCI Score']}
            />
            <Area
              type="monotone"
              dataKey="vci_score"
              stroke="#10b981"
              strokeWidth={2}
              fill="url(#vciGradient)"
              dot={{ fill: '#10b981', strokeWidth: 0, r: 3 }}
              activeDot={{ fill: '#10b981', strokeWidth: 2, stroke: '#fff', r: 5 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}
