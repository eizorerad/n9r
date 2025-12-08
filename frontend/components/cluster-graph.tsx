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
      <div className="text-muted-foreground">Loading graph...</div>
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

const statusColors: Record<string, string> = {
  healthy: '#10b981', // emerald-500
  moderate: '#f59e0b', // amber-500
  scattered: '#ef4444', // red-500
}

const outlierColor = '#64748b' // slate-500

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
      nodes.push({
        id: `cluster-${cluster.id}`,
        name: cluster.name,
        val: Math.max(cluster.chunk_count * 2, 10), // Node size based on chunk count
        color: statusColors[cluster.status] || statusColors.moderate,
        type: 'cluster',
        data: cluster,
      })
    })

    // Add outlier nodes
    outliers.forEach((outlier, idx) => {
      nodes.push({
        id: `outlier-${idx}`,
        name: outlier.chunk_name || outlier.file_path.split('/').pop() || 'Unknown',
        val: 5, // Smaller size for outliers
        color: outlierColor,
        type: 'outlier',
        data: outlier,
      })

      // Link outliers to their nearest cluster if we can determine it
      // For now, we'll connect outliers to a random cluster to show relationships
      if (clusters.length > 0 && outlier.nearest_file) {
        // Try to find which cluster the nearest file belongs to
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
    // This creates a more connected graph visualization
    for (let i = 0; i < clusters.length; i++) {
      for (let j = i + 1; j < clusters.length; j++) {
        // Connect clusters that share the same dominant language
        if (clusters[i].dominant_language && 
            clusters[i].dominant_language === clusters[j].dominant_language) {
          links.push({
            source: `cluster-${clusters[i].id}`,
            target: `cluster-${clusters[j].id}`,
            value: 0.3,
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
    
    // Center on clicked node
    if (graphRef.current && node.x !== undefined && node.y !== undefined) {
      graphRef.current.centerAt(node.x, node.y, 400)
      graphRef.current.zoom(2, 400)
    }
  }, [onNodeClick])

  // Custom node rendering
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const label = node.name
    const fontSize = Math.max(12 / globalScale, 4)
    const nodeSize = Math.sqrt(node.val) * 2
    const x = node.x ?? 0
    const y = node.y ?? 0

    // Draw node circle
    ctx.beginPath()
    ctx.arc(x, y, nodeSize, 0, 2 * Math.PI)
    ctx.fillStyle = node.color
    ctx.fill()

    // Draw border for outliers
    if (node.type === 'outlier') {
      ctx.strokeStyle = '#f59e0b' // amber border for outliers
      ctx.lineWidth = 2 / globalScale
      ctx.stroke()
    }

    // Draw label
    ctx.font = `${fontSize}px Sans-Serif`
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillStyle = '#e2e8f0' // slate-200
    ctx.fillText(label, x, y + nodeSize + fontSize)
  }, [])

  // Link rendering
  const linkColor = useCallback(() => 'rgba(148, 163, 184, 0.3)', []) // slate-400 with opacity

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        No clusters to visualize
      </div>
    )
  }

  return (
    <div ref={containerRef} className="relative w-full" style={{ height }}>
      {/* Zoom Controls */}
      <div className="absolute top-2 right-2 z-10 flex flex-col gap-1">
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8 bg-background/80 backdrop-blur-sm"
          onClick={handleZoomIn}
          title="Zoom In"
        >
          <ZoomIn className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8 bg-background/80 backdrop-blur-sm"
          onClick={handleZoomOut}
          title="Zoom Out"
        >
          <ZoomOut className="h-4 w-4" />
        </Button>
        <Button
          variant="outline"
          size="icon"
          className="h-8 w-8 bg-background/80 backdrop-blur-sm"
          onClick={handleFitToView}
          title="Fit to View"
        >
          <Maximize2 className="h-4 w-4" />
        </Button>
      </div>

      {/* Force Graph */}
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        width={dimensions.width}
        height={dimensions.height}
        nodeCanvasObject={nodeCanvasObject}
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
          const nodeSize = Math.sqrt(node.val) * 2
          const x = node.x ?? 0
          const y = node.y ?? 0
          ctx.beginPath()
          ctx.arc(x, y, nodeSize + 5, 0, 2 * Math.PI)
          ctx.fillStyle = color
          ctx.fill()
        }}
        linkColor={linkColor}
        linkWidth={1}
        linkDirectionalParticles={0}
        onNodeClick={handleNodeClick}
        cooldownTicks={100}
        onEngineStop={() => graphRef.current?.zoomToFit(400, 50)}
        backgroundColor="transparent"
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  )
}
