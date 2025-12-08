'use client'

import { useState, useCallback, useMemo } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import {
  ArrowLeft,
  MessageSquare,
  GitPullRequest,
  FileCode,
  X,
  PanelLeftClose,
  PanelLeft,
  AlertCircle,
  Loader2,
  RefreshCw,
  GitBranch,
  Clock,
  ShieldAlert,
  FileWarning
} from 'lucide-react'
import { FileTree, FileNode } from '@/components/file-tree'
import { ChatPanel } from '@/components/chat-panel'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { ApiError, branchApi } from '@/lib/api'
import { useFileTreeWithToken, useFileContentWithToken, FileItem } from '@/lib/hooks/use-file-browser'
import { useRepository } from '@/lib/hooks/use-repositories'
import { useQuery } from '@tanstack/react-query'

// Lazy load Monaco Editor components to improve initial page load
const CodeEditor = dynamic(
  () => import('@/components/code-editor').then(mod => mod.CodeEditor),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-muted/20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
)

const DiffEditor = dynamic(
  () => import('@/components/code-editor').then(mod => mod.DiffEditor),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-muted/20">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }
)

interface Tab {
  path: string
  name: string
  isDiff?: boolean
}

// Convert API files to FileNode tree structure with lazy loading support
function buildLazyFileTree(
  files: FileItem[],
  loadedDirectories: Map<string, FileItem[]>
): FileNode[] {
  return files.map(file => {
    if (file.type === 'directory') {
      const children = loadedDirectories.get(file.path)
      return {
        name: file.name,
        path: file.path,
        type: file.type,
        size: file.size,
        isLoaded: children !== undefined,
        children: children ? buildLazyFileTree(children, loadedDirectories) : undefined,
      }
    }
    return {
      name: file.name,
      path: file.path,
      type: file.type,
      size: file.size,
      isLoaded: true,
    }
  })
}

// File tree skeleton
function FileTreeSkeleton() {
  return (
    <div className="p-3 space-y-2">
      {[...Array(8)].map((_, i) => (
        <div key={i} className="flex items-center gap-2" style={{ paddingLeft: `${(i % 3) * 12}px` }}>
          <Skeleton className="h-4 w-4" />
          <Skeleton className="h-4 flex-1" style={{ maxWidth: `${120 - (i % 3) * 20}px` }} />
        </div>
      ))}
    </div>
  )
}

// Error display component
function ErrorDisplay({
  error,
  onRetry,
  title = "Failed to load"
}: {
  error: Error | null
  onRetry?: () => void
  title?: string
}) {
  let errorIcon = <AlertCircle className="h-8 w-8 text-destructive mb-3" />
  let errorTitle = title
  let errorMessage = error?.message || "An unexpected error occurred"
  let showRetry = true

  if (error instanceof ApiError) {
    if (error.isRateLimitError()) {
      errorIcon = <Clock className="h-8 w-8 text-amber-500 mb-3" />
      errorTitle = "Rate limit exceeded"
      errorMessage = "GitHub API rate limit reached. Please wait a moment."
    } else if (error.isPermissionError()) {
      errorIcon = <ShieldAlert className="h-8 w-8 text-destructive mb-3" />
      errorTitle = "Access denied"
      errorMessage = "You don't have permission to access this repository."
      showRetry = false
    } else if (error.isAuthenticationError()) {
      errorIcon = <ShieldAlert className="h-8 w-8 text-destructive mb-3" />
      errorTitle = "Authentication required"
      errorMessage = "Please log in again to continue."
      showRetry = false
    } else if (error.message.includes('binary')) {
      errorIcon = <FileWarning className="h-8 w-8 text-amber-500 mb-3" />
      errorTitle = "Binary file"
      errorMessage = "This file cannot be displayed in the editor."
      showRetry = false
    } else if (error.message.includes('too large')) {
      errorIcon = <FileWarning className="h-8 w-8 text-amber-500 mb-3" />
      errorTitle = "File too large"
      errorMessage = "This file exceeds the size limit for viewing."
      showRetry = false
    }
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      {errorIcon}
      <p className="text-sm font-medium mb-1">{errorTitle}</p>
      <p className="text-xs text-muted-foreground mb-4 max-w-[250px]">{errorMessage}</p>
      {showRetry && onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      )}
    </div>
  )
}

interface IDEClientProps {
  id: string
  token: string
}

export function IDEClient({ id, token }: IDEClientProps) {
  // UI state
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [openTabs, setOpenTabs] = useState<Tab[]>([])
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [showChat, setShowChat] = useState(false)
  const [showFileTree, setShowFileTree] = useState(true)
  const [showDiff, setShowDiff] = useState(false)
  const [selectedBranch, setSelectedBranch] = useState<string>('')

  // Track loaded directories for lazy loading
  const [loadedDirectories, setLoadedDirectories] = useState<Map<string, FileItem[]>>(new Map())

  // Fetch repository info
  const { data: repository, isLoading: repoLoading } = useRepository(id)

  // Fetch branches
  const { data: branchesData } = useQuery({
    queryKey: ['branches', id],
    queryFn: () => branchApi.list(token, id),
    enabled: !!token && !!id,
    staleTime: 5 * 60 * 1000,
  })

  // Use default branch if none selected
  const currentBranch = selectedBranch || repository?.default_branch

  // Fetch file tree with token passed explicitly
  const {
    rootFiles,
    isLoading: filesLoading,
    error: filesError,
    refetch: refetchFiles,
    loadDirectory,
    isDirectoryLoading,
  } = useFileTreeWithToken(id, token, currentBranch)

  // Fetch file content for active tab
  const {
    data: fileContent,
    isLoading: contentLoading,
    error: contentError,
    refetch: refetchContent,
  } = useFileContentWithToken(id, token, activeTab, currentBranch)

  // Debug logging
  console.log('[IDE Debug]', {
    id,
    hasToken: !!token,
    selectedBranch,
    currentBranch,
    repositoryDefaultBranch: repository?.default_branch,
    rootFilesLength: rootFiles?.length,
    filesLoading,
    filesError: filesError?.message,
    loadedDirectoriesSize: loadedDirectories.size,
  })

  // Build file tree with loaded directories
  const fileTree = useMemo(() => {
    if (!rootFiles) return []
    return buildLazyFileTree(rootFiles, loadedDirectories)
  }, [rootFiles, loadedDirectories])

  // Handle directory expansion (lazy loading)
  const handleDirectoryExpand = useCallback(async (path: string) => {
    if (loadedDirectories.has(path)) return

    try {
      await loadDirectory(path)
      // Fetch the directory contents directly
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1'}/repositories/${id}/files?path=${encodeURIComponent(path)}${currentBranch ? `&ref=${encodeURIComponent(currentBranch)}` : ''}`,
        {
          headers: { Authorization: `Bearer ${token}` },
        }
      )
      if (response.ok) {
        const data = await response.json()
        setLoadedDirectories(prev => new Map(prev).set(path, data.data))
      }
    } catch (error) {
      console.error('Failed to load directory:', path, error)
    }
  }, [loadDirectory, loadedDirectories, id, currentBranch, token])

  // Handle file selection
  const handleFileSelect = useCallback((path: string, type: 'file' | 'directory') => {
    if (type === 'file') {
      setSelectedFile(path)

      // Add to tabs if not already open
      if (!openTabs.find(t => t.path === path)) {
        const name = path.split('/').pop() || path
        setOpenTabs(prev => [...prev, { path, name }])
      }
      setActiveTab(path)
    }
  }, [openTabs])

  // Handle closing a tab
  const handleCloseTab = useCallback((path: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setOpenTabs(prev => prev.filter(t => t.path !== path))
    if (activeTab === path) {
      const remaining = openTabs.filter(t => t.path !== path)
      setActiveTab(remaining.length > 0 ? remaining[remaining.length - 1].path : null)
      if (remaining.length === 0) {
        setSelectedFile(null)
      }
    }
  }, [activeTab, openTabs])

  // Handle branch change
  const handleBranchChange = useCallback((branch: string) => {
    setSelectedBranch(branch)
    // Clear loaded directories when switching branches
    setLoadedDirectories(new Map())
    // Clear tabs and selection
    setOpenTabs([])
    setActiveTab(null)
    setSelectedFile(null)
  }, [])

  // Get current tab data
  const activeTabData = openTabs.find(t => t.path === activeTab)

  // Check if directory is loading
  const checkDirectoryLoading = useCallback((path: string) => {
    return isDirectoryLoading(path)
  }, [isDirectoryLoading])

  // Loading state for the whole page
  if (repoLoading) {
    return (
      <div className="h-screen bg-background flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background">
      {/* Top bar */}
      <header className="h-12 border-b border-border bg-muted/30 flex items-center px-4 gap-4 flex-shrink-0">
        <Link href={`/dashboard/repository/${id}`}>
          <Button variant="ghost" size="sm" className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back to Dashboard
          </Button>
        </Link>

        <div className="h-4 w-px bg-border" />

        <div className="flex items-center gap-2">
          <img 
            src="/logo.svg" 
            alt="Necromancer" 
            className="w-6 h-6"
          />
          <span className="font-medium text-sm text-neutral-200">Web IDE</span>
          {repository && (
            <span className="text-neutral-400 text-sm font-mono">
              — {repository.full_name}
            </span>
          )}
        </div>

        <div className="flex-1" />

        {/* Branch selector */}
        {branchesData?.data && branchesData.data.length > 0 && (
          <Select value={currentBranch || ''} onValueChange={handleBranchChange}>
            <SelectTrigger className="w-[180px] h-8">
              <GitBranch className="h-4 w-4 mr-2 text-muted-foreground" />
              <SelectValue placeholder="Select branch" />
            </SelectTrigger>
            <SelectContent>
              {branchesData.data.map((branch) => (
                <SelectItem key={branch.name} value={branch.name}>
                  {branch.name}
                  {branch.is_default && (
                    <span className="ml-2 text-xs text-muted-foreground">(default)</span>
                  )}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDiff(!showDiff)}
            className={cn(showDiff && 'bg-muted')}
            disabled={!activeTabData}
          >
            <GitPullRequest className="h-4 w-4 mr-1" />
            Diff View
          </Button>

          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowChat(!showChat)}
            className={cn(showChat && 'bg-muted')}
          >
            <MessageSquare className="h-4 w-4 mr-1" />
            Chat
          </Button>
        </div>
      </header>

      <div className="flex-1 flex overflow-hidden">
        {/* File Explorer Sidebar */}
        {showFileTree && (
          <aside className="w-64 border-r border-border flex flex-col bg-muted/10 flex-shrink-0">
            <div className="h-10 px-3 flex items-center justify-between border-b border-border">
              <span className="text-sm font-medium text-muted-foreground">Explorer</span>
              <button
                onClick={() => setShowFileTree(false)}
                className="p-1 hover:bg-muted rounded transition-colors"
              >
                <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              {filesLoading || repoLoading ? (
                <FileTreeSkeleton />
              ) : filesError ? (
                <ErrorDisplay error={filesError} onRetry={refetchFiles} title="Failed to load files" />
              ) : fileTree.length === 0 ? (
                <div className="p-4 text-center text-muted-foreground text-sm">
                  No files found
                </div>
              ) : (
                <FileTree
                  files={fileTree}
                  selectedPath={selectedFile || undefined}
                  onSelect={handleFileSelect}
                  onExpand={handleDirectoryExpand}
                  isLoading={checkDirectoryLoading}
                />
              )}
            </div>
          </aside>
        )}

        {/* Toggle sidebar button when hidden */}
        {!showFileTree && (
          <button
            onClick={() => setShowFileTree(true)}
            className="w-10 border-r border-border bg-muted/10 flex items-center justify-center hover:bg-muted transition-colors"
          >
            <PanelLeft className="h-4 w-4 text-muted-foreground" />
          </button>
        )}

        {/* Editor Area */}
        <main className="flex-1 flex flex-col overflow-hidden bg-background">
          {/* Tabs */}
          <div className="h-10 bg-muted/30 border-b border-border flex items-center overflow-x-auto flex-shrink-0">
            {openTabs.map((tab) => (
              <button
                key={tab.path}
                onClick={() => setActiveTab(tab.path)}
                className={cn(
                  'h-full px-4 flex items-center gap-2 border-r border-border text-sm hover:bg-muted/50 transition-colors min-w-0',
                  activeTab === tab.path 
                    ? 'bg-background text-foreground border-t-2 border-t-primary' 
                    : 'text-muted-foreground bg-muted/30'
                )}
                title={tab.path}
              >
                <FileCode className="h-4 w-4 flex-shrink-0" />
                <span className="truncate max-w-[150px]">{tab.name}</span>
                <button
                  onClick={(e) => handleCloseTab(tab.path, e)}
                  className="p-0.5 hover:bg-muted rounded ml-1 flex-shrink-0"
                >
                  <X className="h-3 w-3" />
                </button>
              </button>
            ))}
          </div>

          {/* Editor Content */}
          <div className="flex-1 overflow-hidden">
            {contentLoading ? (
              <div className="h-full w-full flex items-center justify-center bg-muted/20">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : contentError ? (
              <ErrorDisplay error={contentError} onRetry={refetchContent} title="Failed to load file" />
            ) : activeTab && fileContent ? (
              showDiff ? (
                <DiffEditor
                  original=""
                  modified={fileContent.content}
                  language={fileContent.language || getLanguageFromPath(activeTab)}
                />
              ) : (
                <CodeEditor
                  value={fileContent.content}
                  language={fileContent.language || getLanguageFromPath(activeTab)}
                  readOnly
                />
              )
            ) : (
              <div className="h-full flex flex-col items-center justify-center text-muted-foreground">
                <FileCode className="h-16 w-16 mb-4 opacity-30" />
                <p className="text-sm">Select a file to view</p>
              </div>
            )}
          </div>
        </main>

        {/* Chat Panel */}
        {showChat && (
          <aside className="w-96 border-l border-border flex-shrink-0 bg-muted/5">
            <ChatPanel
              repositoryId={id}
              contextFile={selectedFile || undefined}
              onClose={() => setShowChat(false)}
            />
          </aside>
        )}
      </div>
    </div>
  )
}

// Helper to detect language from file path
function getLanguageFromPath(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase()
  const languageMap: Record<string, string> = {
    'ts': 'typescript',
    'tsx': 'typescript',
    'js': 'javascript',
    'jsx': 'javascript',
    'py': 'python',
    'rb': 'ruby',
    'go': 'go',
    'rs': 'rust',
    'java': 'java',
    'kt': 'kotlin',
    'swift': 'swift',
    'c': 'c',
    'cpp': 'cpp',
    'h': 'c',
    'hpp': 'cpp',
    'cs': 'csharp',
    'php': 'php',
    'html': 'html',
    'css': 'css',
    'scss': 'scss',
    'less': 'less',
    'json': 'json',
    'yaml': 'yaml',
    'yml': 'yaml',
    'xml': 'xml',
    'md': 'markdown',
    'sql': 'sql',
    'sh': 'shell',
    'bash': 'shell',
    'zsh': 'shell',
    'dockerfile': 'dockerfile',
    'toml': 'toml',
    'ini': 'ini',
    'env': 'plaintext',
  }
  return languageMap[ext || ''] || 'plaintext'
}
