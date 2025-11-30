'use client'

import { useState, use } from 'react'
import dynamic from 'next/dynamic'
import Link from 'next/link'
import {
  ArrowLeft,
  MessageSquare,
  GitPullRequest,
  FileCode,
  X,
  PanelLeftClose,
  PanelLeft
} from 'lucide-react'
import { FileTree, buildFileTree } from '@/components/file-tree'
import { ChatPanel } from '@/components/chat-panel'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

// Lazy load Monaco Editor components to improve initial page load
const CodeEditor = dynamic(
  () => import('@/components/code-editor').then(mod => mod.CodeEditor),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-gray-900">
        <div className="text-gray-400 text-sm">Loading editor...</div>
      </div>
    )
  }
)

const DiffEditor = dynamic(
  () => import('@/components/code-editor').then(mod => mod.DiffEditor),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-gray-900">
        <div className="text-gray-400 text-sm">Loading diff viewer...</div>
      </div>
    )
  }
)

interface Tab {
  path: string
  name: string
  content: string
  isDiff?: boolean
  original?: string
}

// Mock data - replace with actual API calls
const mockFiles = [
  'src/index.ts',
  'src/app.ts',
  'src/utils/helpers.ts',
  'src/utils/validators.ts',
  'src/components/Button.tsx',
  'src/components/Card.tsx',
  'src/api/client.ts',
  'src/api/types.ts',
  'package.json',
  'tsconfig.json',
  'README.md',
]

const mockFileContent: Record<string, string> = {
  'src/index.ts': `import { app } from './app';

const PORT = process.env.PORT || 3000;

app.listen(PORT, () => {
  console.log(\`Server running on port \${PORT}\`);
});
`,
  'src/app.ts': `import express from 'express';

export const app = express();

app.use(express.json());

app.get('/health', (req, res) => {
  res.json({ status: 'ok' });
});
`,
  'src/utils/helpers.ts': `export function formatDate(date: Date): string {
  return date.toISOString().split('T')[0];
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/(^-|-$)/g, '');
}

// TODO: This function is too complex
export function processData(data: any[]) {
  let result = [];
  for (let i = 0; i < data.length; i++) {
    if (data[i].type === 'a') {
      result.push({ ...data[i], processed: true });
    } else if (data[i].type === 'b') {
      result.push({ ...data[i], processed: false });
    } else {
      // More processing logic...
    }
  }
  return result;
}
`,
}

export default function IDEPage({
  params
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)

  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [openTabs, setOpenTabs] = useState<Tab[]>([])
  const [activeTab, setActiveTab] = useState<string | null>(null)
  const [showChat, setShowChat] = useState(false)
  const [showFileTree, setShowFileTree] = useState(true)
  const [showDiff, setShowDiff] = useState(false)

  const fileTree = buildFileTree(mockFiles)

  const handleFileSelect = (path: string, type: 'file' | 'directory') => {
    if (type === 'file') {
      setSelectedFile(path)

      // Add to tabs if not already open
      if (!openTabs.find(t => t.path === path)) {
        const name = path.split('/').pop() || path
        const content = mockFileContent[path] || `// Content of ${path}`
        setOpenTabs(prev => [...prev, { path, name, content }])
      }
      setActiveTab(path)
    }
  }

  const handleCloseTab = (path: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setOpenTabs(prev => prev.filter(t => t.path !== path))
    if (activeTab === path) {
      const remaining = openTabs.filter(t => t.path !== path)
      setActiveTab(remaining.length > 0 ? remaining[remaining.length - 1].path : null)
    }
  }

  const activeTabData = openTabs.find(t => t.path === activeTab)

  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      {/* Header */}
      <header className="h-12 border-b border-border bg-muted/30 flex items-center px-4 gap-4 flex-shrink-0">
        <Link
          href={`/dashboard/repository/${id}`}
          className="flex items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span className="text-sm">Back</span>
        </Link>

        <div className="h-4 w-px bg-border" />

        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded flex items-center justify-center font-bold text-xs shadow-sm">
            n9
          </div>
          <span className="font-medium text-sm">Web IDE</span>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setShowDiff(!showDiff)}
            className={cn(showDiff && 'bg-muted')}
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

      {/* Main Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* File Tree Sidebar */}
        {showFileTree && (
          <aside className="w-64 border-r border-border bg-muted/10 flex flex-col flex-shrink-0">
            <div className="h-10 px-3 flex items-center justify-between border-b border-border">
              <span className="text-xs font-medium text-muted-foreground uppercase">Explorer</span>
              <button
                onClick={() => setShowFileTree(false)}
                className="p-1 hover:bg-muted rounded transition-colors"
              >
                <PanelLeftClose className="h-4 w-4 text-muted-foreground" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto">
              <FileTree
                files={fileTree}
                selectedPath={selectedFile || undefined}
                onSelect={handleFileSelect}
              />
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
                  'h-full px-4 flex items-center gap-2 border-r border-border text-sm hover:bg-muted/50 transition-colors',
                  activeTab === tab.path ? 'bg-background text-foreground border-t-2 border-t-primary' : 'text-muted-foreground bg-muted/30'
                )}
              >
                <FileCode className="h-4 w-4" />
                <span>{tab.name}</span>
                <button
                  onClick={(e) => handleCloseTab(tab.path, e)}
                  className="p-0.5 hover:bg-muted rounded ml-1"
                >
                  <X className="h-3 w-3" />
                </button>
              </button>
            ))}
          </div>

          {/* Editor Content */}
          <div className="flex-1 overflow-hidden">
            {showDiff && activeTabData ? (
              <DiffEditor
                original={activeTabData.content}
                modified={activeTabData.content.replace(
                  '// TODO: This function is too complex',
                  '// Refactored for clarity'
                )}
                modifiedPath={activeTabData.path}
              />
            ) : activeTabData ? (
              <CodeEditor
                value={activeTabData.content}
                path={activeTabData.path}
                readOnly
                highlightLines={[15, 16, 17]}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-muted-foreground">
                <div className="text-center">
                  <FileCode className="h-12 w-12 mx-auto mb-4 opacity-20" />
                  <p>Select a file to view</p>
                </div>
              </div>
            )}
          </div>
        </main>

        {/* Chat Panel */}
        {showChat && (
          <aside className="w-96 flex-shrink-0 border-l border-border bg-background">
            <ChatPanel
              repositoryId={id}
              contextFile={activeTab || undefined}
              onClose={() => setShowChat(false)}
            />
          </aside>
        )}
      </div>
    </div>
  )
}
