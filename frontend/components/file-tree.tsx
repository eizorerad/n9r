'use client'

import { useState } from 'react'
import { ChevronRight, ChevronDown, File, Folder, FolderOpen } from 'lucide-react'
import { cn } from '@/lib/utils'

export interface FileNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileNode[]
}

interface FileTreeProps {
  files: FileNode[]
  selectedPath?: string
  onSelect?: (path: string, type: 'file' | 'directory') => void
  className?: string
}

interface FileTreeItemProps {
  node: FileNode
  level: number
  selectedPath?: string
  onSelect?: (path: string, type: 'file' | 'directory') => void
}

// File icon based on extension
const fileIcons: Record<string, { color: string }> = {
  '.ts': { color: 'text-blue-400' },
  '.tsx': { color: 'text-blue-400' },
  '.js': { color: 'text-yellow-400' },
  '.jsx': { color: 'text-yellow-400' },
  '.py': { color: 'text-green-400' },
  '.json': { color: 'text-yellow-300' },
  '.md': { color: 'text-gray-400' },
  '.css': { color: 'text-purple-400' },
  '.scss': { color: 'text-pink-400' },
  '.html': { color: 'text-orange-400' },
  '.yaml': { color: 'text-red-400' },
  '.yml': { color: 'text-red-400' },
  '.go': { color: 'text-cyan-400' },
  '.rs': { color: 'text-orange-500' },
  '.rb': { color: 'text-red-500' },
}

function getFileColor(name: string): string {
  const ext = name.substring(name.lastIndexOf('.')).toLowerCase()
  return fileIcons[ext]?.color || 'text-gray-400'
}

function FileTreeItem({ node, level, selectedPath, onSelect }: FileTreeItemProps) {
  const [isOpen, setIsOpen] = useState(level < 2) // Auto-expand first 2 levels
  const isSelected = selectedPath === node.path
  const isDirectory = node.type === 'directory'

  const handleClick = () => {
    if (isDirectory) {
      setIsOpen(!isOpen)
    }
    onSelect?.(node.path, node.type)
  }

  return (
    <div>
      <button
        onClick={handleClick}
        className={cn(
          'w-full flex items-center gap-1 px-2 py-1 text-sm hover:bg-gray-800/50 rounded transition-colors text-left',
          isSelected && 'bg-gray-800 text-white',
          !isSelected && 'text-gray-300'
        )}
        style={{ paddingLeft: `${level * 12 + 8}px` }}
      >
        {/* Expand/collapse icon for directories */}
        {isDirectory ? (
          <span className="w-4 h-4 flex items-center justify-center">
            {isOpen ? (
              <ChevronDown className="h-3 w-3 text-gray-500" />
            ) : (
              <ChevronRight className="h-3 w-3 text-gray-500" />
            )}
          </span>
        ) : (
          <span className="w-4" />
        )}

        {/* Icon */}
        {isDirectory ? (
          isOpen ? (
            <FolderOpen className="h-4 w-4 text-yellow-500 flex-shrink-0" />
          ) : (
            <Folder className="h-4 w-4 text-yellow-500 flex-shrink-0" />
          )
        ) : (
          <File className={cn('h-4 w-4 flex-shrink-0', getFileColor(node.name))} />
        )}

        {/* Name */}
        <span className="truncate">{node.name}</span>
      </button>

      {/* Children */}
      {isDirectory && isOpen && node.children && (
        <div>
          {node.children.map((child) => (
            <FileTreeItem
              key={child.path}
              node={child}
              level={level + 1}
              selectedPath={selectedPath}
              onSelect={onSelect}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export function FileTree({ files, selectedPath, onSelect, className }: FileTreeProps) {
  if (!files || files.length === 0) {
    return (
      <div className={cn('p-4 text-gray-500 text-sm', className)}>
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
    <div className={cn('py-2', className)}>
      {sortedFiles.map((node) => (
        <FileTreeItem
          key={node.path}
          node={node}
          level={0}
          selectedPath={selectedPath}
          onSelect={onSelect}
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
