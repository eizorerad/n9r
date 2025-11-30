'use client'

import { useRef, useEffect } from 'react'
import Editor, { Monaco, OnMount, DiffEditor as MonacoDiffEditor } from '@monaco-editor/react'
import { cn } from '@/lib/utils'

// Types for monaco editor
type IStandaloneCodeEditor = Parameters<OnMount>[0]

interface CodeEditorProps {
  value: string
  language?: string
  path?: string
  readOnly?: boolean
  onChange?: (value: string | undefined) => void
  onMount?: (editor: IStandaloneCodeEditor, monaco: Monaco) => void
  highlightLines?: number[]
  className?: string
}

// Language detection by file extension
const languageMap: Record<string, string> = {
  '.js': 'javascript',
  '.jsx': 'javascript',
  '.ts': 'typescript',
  '.tsx': 'typescript',
  '.py': 'python',
  '.rb': 'ruby',
  '.go': 'go',
  '.rs': 'rust',
  '.java': 'java',
  '.c': 'c',
  '.cpp': 'cpp',
  '.h': 'c',
  '.hpp': 'cpp',
  '.cs': 'csharp',
  '.php': 'php',
  '.swift': 'swift',
  '.kt': 'kotlin',
  '.scala': 'scala',
  '.r': 'r',
  '.sql': 'sql',
  '.sh': 'shell',
  '.bash': 'shell',
  '.zsh': 'shell',
  '.yaml': 'yaml',
  '.yml': 'yaml',
  '.json': 'json',
  '.xml': 'xml',
  '.html': 'html',
  '.htm': 'html',
  '.css': 'css',
  '.scss': 'scss',
  '.less': 'less',
  '.md': 'markdown',
  '.vue': 'vue',
  '.svelte': 'svelte',
}

function getLanguageFromPath(path: string): string {
  const ext = path.substring(path.lastIndexOf('.')).toLowerCase()
  return languageMap[ext] || 'plaintext'
}

export function CodeEditor({
  value,
  language,
  path,
  readOnly = false,
  onChange,
  onMount,
  highlightLines,
  className,
}: CodeEditorProps) {
  const editorRef = useRef<IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<Monaco | null>(null)

  const detectedLanguage = language || (path ? getLanguageFromPath(path) : 'plaintext')

  const handleMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco

    // Configure editor settings
    editor.updateOptions({
      minimap: { enabled: false },
      scrollBeyondLastLine: false,
      fontSize: 13,
      fontFamily: 'JetBrains Mono, Fira Code, Monaco, Menlo, monospace',
      lineNumbers: 'on',
      renderLineHighlight: 'line',
      automaticLayout: true,
      readOnly,
      wordWrap: 'on',
    })

    // Apply highlight decorations if specified
    if (highlightLines && highlightLines.length > 0) {
      const decorations = highlightLines.map(line => ({
        range: new monaco.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: 'bg-yellow-500/20',
          glyphMarginClassName: 'bg-yellow-500',
        },
      }))
      editor.createDecorationsCollection(decorations)
    }

    onMount?.(editor, monaco)
  }

  // Update decorations when highlightLines change
  useEffect(() => {
    if (editorRef.current && monacoRef.current && highlightLines) {
      const decorations = highlightLines.map(line => ({
        range: new monacoRef.current!.Range(line, 1, line, 1),
        options: {
          isWholeLine: true,
          className: 'bg-yellow-500/20',
        },
      }))
      editorRef.current.createDecorationsCollection(decorations)
    }
  }, [highlightLines])

  return (
    <div className={cn('h-full w-full', className)}>
      <Editor
        height="100%"
        defaultLanguage={detectedLanguage}
        language={detectedLanguage}
        value={value}
        theme="vs-dark"
        onChange={onChange}
        onMount={handleMount}
        options={{
          readOnly,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          lineNumbers: 'on',
          automaticLayout: true,
        }}
        loading={
          <div className="h-full w-full flex items-center justify-center bg-gray-900">
            <div className="text-gray-400 text-sm">Loading editor...</div>
          </div>
        }
      />
    </div>
  )
}


// Diff Editor Component
interface DiffEditorProps {
  original: string
  modified: string
  language?: string
  originalPath?: string
  modifiedPath?: string
  renderSideBySide?: boolean
  className?: string
}

export function DiffEditor({
  original,
  modified,
  language,
  originalPath,
  modifiedPath,
  renderSideBySide = true,
  className,
}: DiffEditorProps) {
  const detectedLanguage = language || 
    (modifiedPath ? getLanguageFromPath(modifiedPath) : 
     originalPath ? getLanguageFromPath(originalPath) : 'plaintext')

  return (
    <div className={cn('h-full w-full', className)}>
      <MonacoDiffEditor
        height="100%"
        language={detectedLanguage}
        theme="vs-dark"
        original={original}
        modified={modified}
        options={{
          readOnly: true,
          renderSideBySide,
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          fontSize: 13,
          automaticLayout: true,
        }}
        loading={
          <div className="h-full w-full flex items-center justify-center bg-gray-900">
            <div className="text-gray-400 text-sm">Loading diff...</div>
          </div>
        }
      />
    </div>
  )
}
