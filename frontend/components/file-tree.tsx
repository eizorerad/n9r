'use client'

import { useState, useCallback } from 'react'
import { ChevronRight, ChevronDown, Folder, FolderOpen, Loader2 } from 'lucide-react'
import { Icon } from '@iconify/react'
import { cn } from '@/lib/utils'

// Import specific icons to bundle them
import fileTypeTs from '@iconify/icons-vscode-icons/file-type-typescript'
import fileTypeTsOfficial from '@iconify/icons-vscode-icons/file-type-typescript-official'
import fileTypeReactTs from '@iconify/icons-vscode-icons/file-type-reactts'
import fileTypeJs from '@iconify/icons-vscode-icons/file-type-js-official'
import fileTypeJsOfficial from '@iconify/icons-vscode-icons/file-type-js-official' // or light
import fileTypeReactjs from '@iconify/icons-vscode-icons/file-type-reactjs'
import fileTypePython from '@iconify/icons-vscode-icons/file-type-python'
import fileTypeHtml from '@iconify/icons-vscode-icons/file-type-html'
import fileTypeCss from '@iconify/icons-vscode-icons/file-type-css'
import fileTypeScss from '@iconify/icons-vscode-icons/file-type-scss'
import fileTypeJson from '@iconify/icons-vscode-icons/file-type-json'
import fileTypeMarkdown from '@iconify/icons-vscode-icons/file-type-markdown'
import fileTypeYaml from '@iconify/icons-vscode-icons/file-type-yaml'
import fileTypeXml from '@iconify/icons-vscode-icons/file-type-xml'
import fileTypeEnv from '@iconify/icons-vscode-icons/file-type-dotenv'
import fileTypeGit from '@iconify/icons-vscode-icons/file-type-git'
import fileTypeDocker from '@iconify/icons-vscode-icons/file-type-docker'
import fileTypeGo from '@iconify/icons-vscode-icons/file-type-go'
import fileTypeRust from '@iconify/icons-vscode-icons/file-type-rust'
import fileTypeRuby from '@iconify/icons-vscode-icons/file-type-ruby'
import fileTypePhP from '@iconify/icons-vscode-icons/file-type-php'
import fileTypeShell from '@iconify/icons-vscode-icons/file-type-shell'
import defaultFile from '@iconify/icons-vscode-icons/default-file'

export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  size?: number | null
  children?: FileNode[]
  // For lazy loading: undefined means not loaded, [] means empty dir
  isLoaded?: boolean
}

interface FileTreeProps {
  files: FileNode[]
  selectedPath?: string
  onSelect?: (path: string, type: 'file' | 'directory') => void
  onExpand?: (path: string) => Promise<void> | void
  isLoading?: (path: string) => boolean
  className?: string
}

interface FileTreeItemProps {
  node: FileNode
  level: number
  selectedPath?: string
  onSelect?: (path: string, type: 'file' | 'directory') => void
  onExpand?: (path: string) => Promise<void> | void
  isLoading?: (path: string) => boolean
}

function getFileIcon(name: string): any {
  const lowerName = name.toLowerCase()

  // Specific filenames
  if (lowerName === 'dockerfile') return fileTypeDocker
  if (lowerName === '.gitignore') return fileTypeGit
  if (lowerName === '.env' || lowerName.startsWith('.env.')) return fileTypeEnv

  const ext = name.substring(name.lastIndexOf('.')).toLowerCase()

  switch (ext) {
    case '.ts': return fileTypeTsOfficial
    case '.tsx': return fileTypeReactTs
    case '.js': return fileTypeJsOfficial
    case '.jsx': return fileTypeReactjs
    case '.py': return fileTypePython
    case '.html': return fileTypeHtml
    case '.css': return fileTypeCss
    case '.scss': return fileTypeScss
    case '.json': return fileTypeJson
    case '.md': return fileTypeMarkdown
    case '.yaml':
    case '.yml': return fileTypeYaml
    case '.xml': return fileTypeXml
    case '.go': return fileTypeGo
    case '.rs': return fileTypeRust
    case '.rb': return fileTypeRuby
    case '.php': return fileTypePhP
    case '.sh':
    case '.bash':
    case '.zsh': return fileTypeShell
    default: return defaultFile
  }
}

function FileTreeItem({ node, level, selectedPath, onSelect, onExpand, isLoading }: FileTreeItemProps) {
  const [isOpen, setIsOpen] = useState(false) // Start all directories closed to ensure data loads on first expand
  const isSelected = selectedPath === node.path
  const isDirectory = node.type === 'directory'
  const isCurrentlyLoading = isLoading?.(node.path) ?? false
  const hasChildren = node.children && node.children.length > 0

  const handleClick = useCallback(async () => {
    if (isDirectory) {
      const newOpenState = !isOpen
      setIsOpen(newOpenState)

      // Trigger lazy loading when expanding a directory that hasn't been loaded
      if (newOpenState && !node.isLoaded && onExpand) {
        await onExpand(node.path)
      }
    }
    onSelect?.(node.path, node.type)
  }, [isDirectory, isOpen, node.path, node.type, node.isLoaded, onExpand, onSelect])

  return (
    <div>
      <div className="relative">
        {/* Indentation guides would go here if we were drawing them purely with CSS lines,
             but typical VS Code structure often just uses padding.
             We can simulate the "active indent guide" if we want, but simple padding is often enough.
             For true VS Code look, typically there is hover effect that spans full width or
             stops at some point. Here we make the button span full width.
          */}
        <button
          onClick={handleClick}
          className={cn(
            'w-full flex items-center gap-1.5 py-[3px] text-[13px] transition-colors text-left group select-none border-l-2 border-transparent',
            isSelected
              ? 'bg-[#37373d] text-white border-l-[#007fd4]' // VS Code style: dark blue-grey bg, brighter white text
              : 'text-[#cccccc] hover:bg-[#2a2d2e] hover:text-white'
          )}
          style={{ paddingLeft: `${level * 12 + 10}px` }}
          title={node.path}
        >
          {/* Expand/collapse icon for directories */}
          <span className="flex items-center justify-center w-4 h-4 flex-shrink-0">
            {isDirectory ? (
              isCurrentlyLoading ? (
                <Loader2 className="h-3 w-3 text-muted-foreground animate-spin" />
              ) : isOpen ? (
                <ChevronDown className="h-3.5 w-3.5 text-[#cccccc]" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5 text-[#cccccc]" />
              )
            ) : (
              // Spacer for files matching the chevron width
              <span className="w-4" />
            )}
          </span>

          {/* Icon - Only for files now, folders just use arrows as requested */}
          {!isDirectory && (
            <Icon icon={getFileIcon(node.name)} className="h-4 w-4 flex-shrink-0" />
          )}

          {/* Name */}
          <span className="truncate leading-none pt-[1px]">{node.name}</span>
        </button>
      </div>

      {/* Children */}
      {isDirectory && isOpen && hasChildren && (
        <div className="relative">
          {/* Optional: Add a vertical line for the tree structure here if desired, 
               but VS Code default is often clean unless configured otherwise. 
           */}
          {node.children!.map((child) => (
            <FileTreeItem
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
              onExpand={onExpand}
              isLoading={isLoading}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FileTree({ files, selectedPath, onSelect, onExpand, isLoading, className }: FileTreeProps) {
  if (!files || files.length === 0) {
    return (
      <div className={cn('p-4 text-muted-foreground text-sm', className)}>
        No files found
      </div>
    )
  }

  // Sort: directories first, then files, alphabetically
  const sortedFiles = [...files].sort((a, b) => {
    if (a.type === b.type) return a.name.localeCompare(b.name)
    return a.type === 'directory' ? -1 : 1
  })

  return (
    <div className={cn('pt-0 pb-2', className)}>
      {sortedFiles.map((node) => (
        <FileTreeItem
          key={node.path}
          node={node}
          level={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
          onExpand={onExpand}
          isLoading={isLoading}
        />
      ))}
    </div>
  )
}

// Helper to convert flat file list to tree structure
export function buildFileTree(paths: string[]): FileNode[] {
  const root: Record<string, FileNode> = {}

  for (const path of paths) {
    const parts = path.split('/')
    let current = root

    for (let i = 0; i < parts.length; i++) {
      const part = parts[i]
      const isFile = i === parts.length - 1
      const currentPath = parts.slice(0, i + 1).join('/')

      if (!current[part]) {
        current[part] = {
          name: part,
          path: currentPath,
          type: isFile ? 'file' : 'directory',
          children: isFile ? undefined : [],
        }
      }

      if (!isFile) {
        // Navigate into directory
        const dirNode = current[part]
        if (!dirNode.children) dirNode.children = []

        // Create lookup for children
        const childLookup: Record<string, FileNode> = {}
        for (const child of dirNode.children) {
          childLookup[child.name] = child
        }
        current = childLookup
      }
    }
  }

  // Convert to array and sort
  function toArray(obj: Record<string, FileNode>): FileNode[] {
    return Object.values(obj)
      .map(node => ({
        ...node,
        children: node.children ? toArray(
          node.children.reduce((acc, child) => {
            acc[child.name] = child
            return acc
          }, {} as Record<string, FileNode>)
        ) : undefined,
      }))
      .sort((a, b) => {
        if (a.type === b.type) return a.name.localeCompare(b.name)
        return a.type === 'directory' ? -1 : 1
      })
  }

  return toArray(root)
}
