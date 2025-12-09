'use client'

import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import dynamic from 'next/dynamic'
import { useSearchParams } from 'next/navigation'
import {
  MessageSquare,

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
import { useCommitSelectionStore } from '@/lib/stores/commit-selection-store'
import { useStatusBarStore } from '@/lib/stores/status-bar-store'

// Lazy load Monaco Editor components to improve initial page load
const CodeEditor = dynamic(
  () => import('@/components/code-editor').then(mod => mod.CodeEditor),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-[#1e1e1e]">
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
  // ... function content remains same ...
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
          <Skeleton className="h-4 w-4 bg-[#2b2b2b]" />
          <Skeleton className="h-4 flex-1 bg-[#2b2b2b]" style={{ maxWidth: `${120 - (i % 3) * 20}px` }} />
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

// cleaned up imports

export function IDEClient({ id, token }: IDEClientProps) {
  const searchParams = useSearchParams()
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [openTabs, setOpenTabs] = useState<Tab[]>([])
  const [activeTab, setActiveTab] = useState<string | null>(null)

  const [showChat, setShowChat] = useState(false)
  const [showFileTree, setShowFileTree] = useState(true)

  const [selectedBranch, setSelectedBranch] = useState<string>('')

  // Global commit selection state
  const { selectedCommitSha, clearSelection } = useCommitSelectionStore()

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

  // Use selected commit SHA if available, otherwise selected branch, otherwise default
  const currentRef = selectedCommitSha || selectedBranch || repository?.default_branch

  // Fetch file tree with token passed explicitly
  const {
    rootFiles,
    isLoading: filesLoading,
    error: filesError,
    refetch: refetchFiles,
    loadDirectory,
    isDirectoryLoading,
  } = useFileTreeWithToken(id, token, currentRef)

  // Fetch file content for active tab
  const {
    data: fileContent,
    isLoading: contentLoading,
    error: contentError,
    refetch: refetchContent,
  } = useFileContentWithToken(id, token, activeTab, currentRef)

  // Debug logging
  console.log('[IDE Debug]', {
    id,
    hasToken: !!token,
    selectedBranch,
    selectedCommitSha,
    currentRef,
    repositoryDefaultBranch: repository?.default_branch,
    rootFilesLength: rootFiles?.length,
    filesLoading,
    filesError: filesError?.message,
    loadedDirectoriesSize: loadedDirectories.size,
  })

  // Status Bar Integration
  const { setFileInfo, setBranch } = useStatusBarStore()

  // Update Status Bar when active tab/file changes
  useEffect(() => {
    if (activeTab) {
      const lang = getLanguageFromPath(activeTab)
      // Format nicely (e.g. 'TypeScript React')
      const formattedLang = lang === 'typescript' && activeTab.endsWith('x') ? 'TypeScript React' :
        lang.charAt(0).toUpperCase() + lang.slice(1)
      setFileInfo(formattedLang)
    } else {
      setFileInfo(null)
    }
  }, [activeTab, setFileInfo])

  // Update Status Bar when branch changes via select
  useEffect(() => {
    if (selectedBranch) {
      setBranch(selectedBranch)
    }
  }, [selectedBranch, setBranch])

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
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1'}/repositories/${id}/files?path=${encodeURIComponent(path)}${currentRef ? `&ref=${encodeURIComponent(currentRef)}` : ''}`,
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
  }, [loadDirectory, loadedDirectories, id, currentRef, token])

  // Handle file selection
  const handleFileSelect = useCallback((path: string, type: 'file' | 'directory') => {
    if (type === 'file') {
      setSelectedFile(path)

      setOpenTabs(prev => {
        if (prev.some(t => t.path === path)) return prev
        const name = path.split('/').pop() || path
        return [...prev, { path, name }]
      })
      setActiveTab(path)
    }
  }, [])

  // Handle URL query params for opening files (e.g. from search)
  // Using a ref to track if we've already processed this file param
  const processedFileParamRef = useRef<string | null>(null)
  useEffect(() => {
    const fileParam = searchParams.get('file')
    if (fileParam && fileParam !== processedFileParamRef.current) {
      processedFileParamRef.current = fileParam
      // Defer state update to avoid synchronous setState in effect
      queueMicrotask(() => {
        handleFileSelect(fileParam, 'file')
      })
    }
  }, [searchParams, handleFileSelect])

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
    clearSelection() // Clear specific commit selection to switch to branch head
    // Clear loaded directories when switching branches
    setLoadedDirectories(new Map())
    // Clear tabs and selection
    setOpenTabs([])
    setActiveTab(null)
    setSelectedFile(null)
  }, [clearSelection])



  // Check if directory is loading
  const checkDirectoryLoading = useCallback((path: string) => {
    return isDirectoryLoading(path)
  }, [isDirectoryLoading])

  // Loading state for the whole page
  if (repoLoading) {
    return (
      <div className="h-full bg-[#1e1e1e] flex items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="h-full flex flex-row overflow-hidden bg-[#1e1e1e] text-[#cccccc]">
      {/* File Explorer Sidebar */}
      {showFileTree && (
        <aside className="w-[300px] flex flex-col bg-[#252526] border-r border-[#2b2b2b] flex-shrink-0">
          <div className="h-9 px-4 flex items-center justify-between bg-[#252526] text-[11px] font-bold text-[#bbbbbb] select-none uppercase tracking-wide">
            <span>Explorer</span>
            <div className="flex items-center gap-1">
              {/* Branch Selector integrated as a small icon/dropdown action if possible, strictly mimicking VS Code '...' menu usually, 
                   but for utility we can keep it simple or just show standard sidebar actions. 
                   For now, let's keep the branch selector useful but compact. */}
              <button onClick={() => setShowFileTree(false)} className="hover:text-white">
                <PanelLeftClose className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Repository Name & Branch - mimics the "Project Name [Branch]" feeling or just top level item */}
          <div className="px-4 py-2 flex flex-col gap-2 border-b border-[#2b2b2b]">
            <div className="flex items-center justify-between text-xs text-[#cccccc] font-medium">
              <span className="truncate">{repository?.name || 'Repository'}</span>
            </div>

            {branchesData?.data && branchesData.data.length > 0 && (
              <Select
                value={(!selectedCommitSha && selectedBranch) ? selectedBranch : ''}
                onValueChange={handleBranchChange}
              >
                <SelectTrigger className="h-6 text-xs bg-[#3c3c3c] border-none text-[#cccccc] px-2 truncate">
                  <GitBranch className="h-3 w-3 mr-1.5 opacity-70 flex-shrink-0" />
                  <SelectValue placeholder={selectedCommitSha ? `Detached at ${selectedCommitSha.substring(0, 7)}` : (selectedBranch || "Select branch")} />
                </SelectTrigger>
                <SelectContent className="bg-[#252526] border-[#454545] text-[#cccccc]">
                  {branchesData.data.map((branch) => (
                    <SelectItem key={branch.name} value={branch.name} className="text-xs focus:bg-[#094771] focus:text-white">
                      {branch.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          <div className="flex-1 overflow-y-auto py-2">
            {filesLoading ? (
              <FileTreeSkeleton />
            ) : filesError ? (
              <ErrorDisplay error={filesError} onRetry={refetchFiles} title="Failed to load files" />
            ) : fileTree.length === 0 ? (
              <div className="p-4 text-center text-muted-foreground text-xs">
                No files found
              </div>
            ) : (
              <FileTree
                files={fileTree}
                selectedPath={selectedFile || undefined}
                onSelect={handleFileSelect}
                onExpand={handleDirectoryExpand}
                isLoading={checkDirectoryLoading}
                className="px-2"
              />
            )}
          </div>
        </aside>
      )}

      {/* Editor Area */}
      <main className="flex-1 flex flex-col min-w-0 bg-[#1e1e1e]">
        {/* Editor Tabs & Actions Bar */}
        <div className="h-9 flex bg-[#252526] overflow-hidden flex-shrink-0">
          {/* Open Tabs */}
          <div className="flex-1 flex overflow-x-auto scrollbar-hide">
            {!showFileTree && (
              <button
                onClick={() => setShowFileTree(true)}
                className="h-full px-3 hover:bg-[#2a2d2e] flex items-center justify-center border-r border-[#2b2b2b]"
                title="Show Explorer"
              >
                <PanelLeft className="h-4 w-4 text-[#858585]" />
              </button>
            )}

            {openTabs.map((tab) => (
              <button
                key={tab.path}
                onClick={() => setActiveTab(tab.path)}
                className={cn(
                  'h-full px-3 flex items-center gap-2 text-xs min-w-fit max-w-[200px] border-r border-[#252526] group select-none',
                  activeTab === tab.path
                    ? 'bg-[#1e1e1e] text-white border-t-2 border-t-[#007fd4]'
                    : 'bg-[#2d2d2d] text-[#969696] hover:bg-[#2a2d2e] border-t-2 border-t-transparent'
                )}
                title={tab.path}
              >
                <FileCode className={cn(
                  "h-3.5 w-3.5 flex-shrink-0",
                  // Try to map icon color if possible, else default
                  activeTab === tab.path ? "text-[#519aba]" : "text-[#969696]"
                )} />
                <span className="truncate">{tab.name}</span>
                <span
                  onClick={(e) => handleCloseTab(tab.path, e)}
                  className={cn(
                    "ml-1 w-5 h-5 flex items-center justify-center rounded-sm hover:bg-[#454545] opacity-0 group-hover:opacity-100 transition-opacity",
                    activeTab === tab.path && "opacity-100" // Always show close on active
                  )}
                >
                  <X className="h-3.5 w-3.5" />
                </span>
              </button>
            ))}
          </div>

          {/* Editor Actions (Diff, Chat) */}
          <div className="flex items-center px-2 gap-1 bg-[#252526]">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowChat(!showChat)}
              className={cn(
                "h-6 px-2 text-xs hover:bg-[#3c3c3c] text-[#cccccc]",
                showChat && "bg-[#3c3c3c] text-white"
              )}
              title="Toggle Chat"
            >
              <MessageSquare className="h-3.5 w-3.5 mr-1.5" />
              Chat
            </Button>
          </div>
        </div>

        {/* Editor Content */}
        <div className="flex-1 overflow-hidden relative">
          {contentLoading ? (
            <div className="h-full w-full flex items-center justify-center bg-[#1e1e1e]">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : contentError ? (
            <ErrorDisplay error={contentError} onRetry={refetchContent} title="Failed to load file" />
          ) : activeTab && fileContent ? (
            <CodeEditor
              value={fileContent.content}
              language={fileContent.language || getLanguageFromPath(activeTab)}
              readOnly
              className="bg-[#1e1e1e]"
            />
          ) : (
            <div className="h-full flex flex-col items-center justify-center text-[#555555]">
              <div className="mb-4">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src="/logo.svg" className="w-24 h-24 opacity-5 grayscale" alt="" />
              </div>
              <p className="text-sm">Select a file to begin editing</p>
              <p className="text-xs mt-2 text-[#444444]">Use ⌘P to search files</p>
            </div>
          )}
        </div>
      </main>

      {/* Chat Panel */}
      {showChat && (
        <aside className="w-80 border-l border-[#2b2b2b] flex-shrink-0 bg-[#252526]">
          <ChatPanel
            repositoryId={id}
            contextFile={selectedFile || undefined}
            onClose={() => setShowChat(false)}
          />
        </aside>
      )}
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
