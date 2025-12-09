'use client'

import { useCallback, useRef, useMemo, useEffect, useState } from 'react'
import dynamic from 'next/dynamic'
import { Button } from '@/components/ui/button'
import { ZoomIn, ZoomOut, Maximize2 } from 'lucide-react'

// Dynamic import for bundle optimization - react-force-graph-2d is a heavy library
const ForceGraph2D = dynamic(() => import('react-force-graph-2d'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-full">
      <div className="text-muted-foreground animate-pulse">Loading graph...</div>
    </div>
  ),
})

interface ClusterInfo {
  id: number
  name: string
  file_count: number
  chunk_count: number
  cohesion: number
  top_files: string[]
  dominant_language: string | null
  status: string
}

interface OutlierInfo {
  file_path: string
  chunk_name: string | null
  chunk_type: string | null
  nearest_similarity: number
  nearest_file: string | null
  suggestion: string
  confidence: number
  confidence_factors: string[]
  tier: string
}

interface GraphNode {
  id: string
  name: string
  val: number
  color: string
  glowColor: string
  type: 'cluster' | 'outlier'
  data: ClusterInfo | OutlierInfo
  // These are added by force-graph at runtime
  x?: number
  y?: number
  vx?: number
  vy?: number
  fx?: number
  fy?: number
}

interface GraphLink {
  source: string
  target: string
  value: number
}

interface GraphData {
  nodes: GraphNode[]
  links: GraphLink[]
}

interface ClusterGraphProps {
  clusters: ClusterInfo[]
  outliers: OutlierInfo[]
  onNodeClick?: (node: GraphNode) => void
  height?: number
}

// Enhanced color palette with gradient support
const statusColors: Record<string, { primary: string; glow: string }> = {
  healthy: { primary: '#10b981', glow: 'rgba(16, 185, 129, 0.6)' },   // emerald
  moderate: { primary: '#f59e0b', glow: 'rgba(245, 158, 11, 0.6)' },  // amber
  scattered: { primary: '#ef4444', glow: 'rgba(239, 68, 68, 0.6)' },  // red
}

const outlierColors = { primary: '#8b5cf6', glow: 'rgba(139, 92, 246, 0.5)' } // violet for outliers

export function ClusterGraph({
  clusters,
  outliers,
  onNodeClick,
  height = 400
}: ClusterGraphProps) {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const graphRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 600, height })
  const [hoveredNode, setHoveredNode] = useState<string | null>(null)

  // Update dimensions on resize
  useEffect(() => {
    const updateDimensions = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.offsetWidth,
          height: height,
        })
      }
    }

    updateDimensions()
    window.addEventListener('resize', updateDimensions)
    return () => window.removeEventListener('resize', updateDimensions)
  }, [height])

  // Transform cluster data into graph format
  const graphData: GraphData = useMemo(() => {
    const nodes: GraphNode[] = []
    const links: GraphLink[] = []

    // Add cluster nodes
    clusters.forEach((cluster) => {
      const colorConfig = statusColors[cluster.status] || statusColors.moderate
      nodes.push({
        id: `cluster-${cluster.id}`,
        name: cluster.name,
        val: Math.max(cluster.chunk_count * 3, 15), // Larger nodes
        color: colorConfig.primary,
        glowColor: colorConfig.glow,
        type: 'cluster',
        data: cluster,
      })
    })

    // Add outlier nodes
    outliers.forEach((outlier, idx) => {
      nodes.push({
        id: `outlier-${idx}`,
        name: outlier.chunk_name || outlier.file_path.split('/').pop() || 'Unknown',
        val: 8, // Slightly larger for visibility
        color: outlierColors.primary,
        glowColor: outlierColors.glow,
        type: 'outlier',
        data: outlier,
      })

      // Link outliers to their nearest cluster
      if (clusters.length > 0 && outlier.nearest_file) {
        const nearestCluster = clusters.find(c =>
          c.top_files.some(f => outlier.nearest_file?.includes(f) || f.includes(outlier.nearest_file || ''))
        )
        if (nearestCluster) {
          links.push({
            source: `outlier-${idx}`,
            target: `cluster-${nearestCluster.id}`,
            value: outlier.nearest_similarity,
          })
        }
      }
    })

    // Create links between clusters based on shared characteristics
    for (let i = 0; i < clusters.length; i++) {
      for (let j = i + 1; j < clusters.length; j++) {
        if (clusters[i].dominant_language &&
          clusters[i].dominant_language === clusters[j].dominant_language) {
          links.push({
            source: `cluster-${clusters[i].id}`,
            target: `cluster-${clusters[j].id}`,
            value: 0.5,
          })
        }
      }
    }

    return { nodes, links }
  }, [clusters, outliers])

  // Zoom controls
  const handleZoomIn = useCallback(() => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom()
      graphRef.current.zoom(currentZoom * 1.3, 400)
    }
  }, [])

  const handleZoomOut = useCallback(() => {
    if (graphRef.current) {
      const currentZoom = graphRef.current.zoom()
      graphRef.current.zoom(currentZoom / 1.3, 400)
    }
  }, [])

  const handleFitToView = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoomToFit(400, 50)
    }
  }, [])

  // Node click handler
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleNodeClick = useCallback((node: any) => {
    onNodeClick?.(node as GraphNode)

    if (graphRef.current && node.x !== undefined && node.y !== undefined) {
      graphRef.current.centerAt(node.x, node.y, 400)
      graphRef.current.zoom(2, 400)
    }
  }, [onNodeClick])

  // Enhanced node rendering with glow effects
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name
    const fontSize = Math.max(11 / globalScale, 3)
    const nodeSize = Math.sqrt(node.val) * 2.5
    const x = node.x ?? 0
    const y = node.y ?? 0
    const isHovered = hoveredNode === node.id

    // Draw outer glow
    const gradient = ctx.createRadialGradient(x, y, nodeSize * 0.5, x, y, nodeSize * 2.5)
    gradient.addColorStop(0, node.glowColor)
    gradient.addColorStop(1, 'transparent')

    ctx.beginPath()
    ctx.arc(x, y, nodeSize * 2.5, 0, 2 * Math.PI)
    ctx.fillStyle = gradient
    ctx.fill()

    // Draw main node with gradient
    const nodeGradient = ctx.createRadialGradient(x - nodeSize * 0.3, y - nodeSize * 0.3, 0, x, y, nodeSize)
    nodeGradient.addColorStop(0, 'rgba(255, 255, 255, 0.3)')
    nodeGradient.addColorStop(0.5, node.color)
    nodeGradient.addColorStop(1, node.color)

    ctx.beginPath()
    ctx.arc(x, y, nodeSize, 0, 2 * Math.PI)
    ctx.fillStyle = nodeGradient
    ctx.fill()

    // Draw border
    ctx.strokeStyle = isHovered ? '#ffffff' : 'rgba(255, 255, 255, 0.3)'
    ctx.lineWidth = isHovered ? 3 / globalScale : 1.5 / globalScale
    ctx.stroke()

    // Draw inner highlight for 3D effect
    ctx.beginPath()
    ctx.arc(x - nodeSize * 0.25, y - nodeSize * 0.25, nodeSize * 0.3, 0, 2 * Math.PI)
    ctx.fillStyle = 'rgba(255, 255, 255, 0.2)'
    ctx.fill()

    // Draw pulsing ring for outliers
    if (node.type === 'outlier') {
      ctx.beginPath()
      ctx.arc(x, y, nodeSize * 1.4, 0, 2 * Math.PI)
      ctx.strokeStyle = 'rgba(139, 92, 246, 0.4)'
      ctx.lineWidth = 2 / globalScale
      ctx.setLineDash([4 / globalScale, 4 / globalScale])
      ctx.stroke()
      ctx.setLineDash([])
    }

    // Draw label with background
    ctx.font = `bold ${fontSize}px Inter, system-ui, sans-serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'

    const textWidth = ctx.measureText(label).width
    const padding = 4 / globalScale
    const labelY = y + nodeSize + fontSize * 1.5

    // Label background
    ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
    ctx.beginPath()
    ctx.roundRect(x - textWidth / 2 - padding, labelY - fontSize / 2 - padding / 2, textWidth + padding * 2, fontSize + padding, 3 / globalScale)
    ctx.fill()

    // Label text
    ctx.fillStyle = '#ffffff'
    ctx.fillText(label, x, labelY)

    // Draw chunk count badge for clusters
    if (node.type === 'cluster') {
      const clusterData = node.data as ClusterInfo
      const badgeText = `${clusterData.chunk_count}`
      const badgeFontSize = Math.max(9 / globalScale, 2.5)
      ctx.font = `bold ${badgeFontSize}px Inter, system-ui, sans-serif`

      const badgeWidth = ctx.measureText(badgeText).width + 6 / globalScale
      const badgeHeight = badgeFontSize + 4 / globalScale
      const badgeX = x + nodeSize * 0.7
      const badgeY = y - nodeSize * 0.7

      // Badge background
      ctx.fillStyle = 'rgba(255, 255, 255, 0.9)'
      ctx.beginPath()
      ctx.roundRect(badgeX - badgeWidth / 2, badgeY - badgeHeight / 2, badgeWidth, badgeHeight, 10 / globalScale)
      ctx.fill()

      // Badge text
      ctx.fillStyle = '#1e1e1e'
      ctx.fillText(badgeText, badgeX, badgeY)
    }
  }, [hoveredNode])

  // Enhanced link rendering
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const source = link.source
    const target = link.target

    if (!source.x || !source.y || !target.x || !target.y) return

    // Create gradient for link
    const gradient = ctx.createLinearGradient(source.x, source.y, target.x, target.y)
    gradient.addColorStop(0, source.glowColor || 'rgba(100, 116, 139, 0.3)')
    gradient.addColorStop(1, target.glowColor || 'rgba(100, 116, 139, 0.3)')

    ctx.beginPath()
    ctx.moveTo(source.x, source.y)
    ctx.lineTo(target.x, target.y)
    ctx.strokeStyle = gradient
    ctx.lineWidth = Math.max(link.value * 3, 1) / globalScale
    ctx.stroke()
  }, [])

  // Node hover handlers
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const handleNodeHover = useCallback((node: any) => {
    setHoveredNode(node?.id || null)
    if (containerRef.current) {
      containerRef.current.style.cursor = node ? 'pointer' : 'default'
    }
  }, [])

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground gap-2">
        <div className="w-16 h-16 rounded-full border-2 border-dashed border-muted-foreground/30 flex items-center justify-center">
          <div className="w-8 h-8 rounded-full bg-muted-foreground/10" />
        </div>
        <span className="text-sm">No clusters to visualize</span>
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative w-full rounded-lg overflow-hidden bg-gradient-to-br from-background via-background to-muted/20" style={{ height }}>
      {/* Subtle grid background */}
      <div
        className="absolute inset-0 opacity-5"
        style={{
          backgroundImage: `radial-gradient(circle at 1px 1px, currentColor 1px, transparent 0)`,
          backgroundSize: '24px 24px',
        }}
      />

      {/* Legend */}
      <div className="absolute top-2 left-2 z-10 flex flex-col gap-1 text-[10px] bg-background/80 backdrop-blur-sm rounded-lg p-2 border border-border/50">
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: statusColors.healthy.primary }} />
          <span className="text-muted-foreground">Healthy</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: statusColors.moderate.primary }} />
          <span className="text-muted-foreground">Moderate</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full" style={{ background: statusColors.scattered.primary }} />
          <span className="text-muted-foreground">Scattered</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-2.5 h-2.5 rounded-full border border-dashed" style={{ background: outlierColors.primary, borderColor: outlierColors.primary }} />
          <span className="text-muted-foreground">Outlier</span>
        </div>
      </div>

      {/* Zoom Controls */}
      <div className="absolute top-2 right-2 z-10 flex flex-col gap-1">
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 bg-background/80 backdrop-blur-sm border-border/50 hover:bg-primary/10"
          onClick={handleZoomIn}
          title="Zoom In"
        >
          <ZoomIn className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 bg-background/80 backdrop-blur-sm border-border/50 hover:bg-primary/10"
          onClick={handleZoomOut}
          title="Zoom Out"
        >
          <ZoomOut className="h-3.5 w-3.5" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-7 w-7 bg-background/80 backdrop-blur-sm border-border/50 hover:bg-primary/10"
          onClick={handleFitToView}
          title="Fit to View"
        >
          <Maximize2 className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Force Graph */}
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        nodeCanvasObject={nodeCanvasObject}
        linkCanvasObject={linkCanvasObject}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
          const nodeSize = Math.sqrt(node.val) * 2.5
          const x = node.x ?? 0
          const y = node.y ?? 0
          ctx.beginPath()
          ctx.arc(x, y, nodeSize + 10, 0, 2 * Math.PI)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkDirectionalParticles={2}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleSpeed={0.005}
        linkDirectionalParticleColor={() => 'rgba(255, 255, 255, 0.5)'}
        onNodeClick={handleNodeClick}
        onNodeHover={handleNodeHover}
        cooldownTicks={100}
        onEngineStop={() => graphRef.current?.zoomToFit(400, 50)}
        backgroundColor="transparent"
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
      />
    </div>
  )
}
