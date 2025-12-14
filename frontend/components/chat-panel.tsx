'use client'

import { useState, useRef, useEffect, memo } from 'react'
import { Send, X, MessageSquare, Loader2, Plus, Settings2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import ReactMarkdown, { Components } from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/cjs/styles/prism'

/**
 * Markdown renderer component for chat messages.
 * Handles code blocks with syntax highlighting, headings, lists, etc.
 */
const MarkdownContent = memo(function MarkdownContent({ children }: { children: string }) {
  const components: Components = {
    code({ className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '')
      const isInline = !match && !String(children).includes('\n')

      if (isInline) {
        return (
          <code
            className="bg-[#2d2d2d] text-[#ce9178] px-1.5 py-0.5 rounded text-[13px] font-mono"
            {...props}
          >
            {children}
          </code>
        )
      }

      return (
        <SyntaxHighlighter
          style={oneDark as Record<string, React.CSSProperties>}
          language={match ? match[1] : 'text'}
          PreTag="div"
          customStyle={{
            margin: '0.5rem 0',
            padding: '0.75rem',
            borderRadius: '6px',
            fontSize: '13px',
            lineHeight: '1.5',
            background: '#1e1e1e',
          }}
          codeTagProps={{
            style: {
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace',
            },
          }}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      )
    },
    h1: ({ children }) => (
      <h1 className="text-lg font-bold mt-4 mb-2 text-[#e0e0e0] border-b border-[#333] pb-1">{children}</h1>
    ),
    h2: ({ children }) => (
      <h2 className="text-base font-bold mt-3 mb-1.5 text-[#e0e0e0]">{children}</h2>
    ),
    h3: ({ children }) => (
      <h3 className="text-sm font-bold mt-2 mb-1 text-[#d4d4d4]">{children}</h3>
    ),
    h4: ({ children }) => (
      <h4 className="text-sm font-semibold mt-2 mb-1 text-[#cccccc]">{children}</h4>
    ),
    p: ({ children }) => (
      <p className="my-2 leading-relaxed">{children}</p>
    ),
    ul: ({ children }) => (
      <ul className="list-disc list-inside my-2 space-y-1">{children}</ul>
    ),
    ol: ({ children }) => (
      <ol className="list-decimal list-inside my-2 space-y-1">{children}</ol>
    ),
    li: ({ children }) => (
      <li className="leading-relaxed">{children}</li>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-[#0e639c] pl-3 my-2 text-[#a0a0a0] italic">
        {children}
      </blockquote>
    ),
    a: ({ href, children }) => (
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="text-[#3794ff] hover:underline"
      >
        {children}
      </a>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-[#e0e0e0]">{children}</strong>
    ),
    em: ({ children }) => (
      <em className="italic">{children}</em>
    ),
    hr: () => <hr className="border-[#333] my-3" />,
    table: ({ children }) => (
      <div className="overflow-x-auto my-2">
        <table className="min-w-full border border-[#333] text-sm">{children}</table>
      </div>
    ),
    thead: ({ children }) => (
      <thead className="bg-[#2d2d2d]">{children}</thead>
    ),
    th: ({ children }) => (
      <th className="px-3 py-1.5 border border-[#333] text-left font-semibold">{children}</th>
    ),
    td: ({ children }) => (
      <td className="px-3 py-1.5 border border-[#333]">{children}</td>
    ),
  }

  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {children}
    </ReactMarkdown>
  )
})

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/v1'

function withIpv4Localhost(url: string): string {
  return url.replace('://localhost', '://127.0.0.1')
}

async function fetchWithLocalhostFallback(input: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(input, init)
  } catch (err) {
    // Common local-dev issue: localhost resolves to IPv6 but server is bound to IPv4 only.
    if (input.includes('://localhost')) {
      const alt = withIpv4Localhost(input)
      console.warn('[chat] fetch failed, retrying with 127.0.0.1', { input, alt, err })
      return await fetch(alt, init)
    }
    throw err
  }
}

type ChatEventType = 'message' | 'assistant' | 'user' | 'tool' | 'thinking' | 'steering' | 'context_source'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
  meta?: {
    type?: ChatEventType
    title?: string
    details?: string
    source?: string  // for context_source events: "rag", "tree", "active_file"
    status?: string  // for context_source events: "found", "empty", "error", "searching", "loading"
    count?: number   // for context_source events: number of items found
  }
}

interface ChatModelInfo {
  id: string
  label: string
  provider: string
  available: boolean
  reason_unavailable?: string | null
  is_default?: boolean
}

interface ChatModelsResponse {
  models: ChatModelInfo[]
  defaults: Record<string, string>
}

interface ChatPanelProps {
  repositoryId: string
  token: string
  threadId?: string
  contextFile?: string
  ref?: string
  activeFile?: string
  openFiles?: string[]
  className?: string
  onClose?: () => void
}

export function ChatPanel({
  repositoryId,
  token,
  threadId: initialThreadId,
  contextFile,
  ref,
  activeFile,
  openFiles,
  className,
  onClose,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [threadId, setThreadId] = useState(initialThreadId)
  const [streamingContent, setStreamingContent] = useState('')
  const [modelsOpen, setModelsOpen] = useState(false)
  const [models, setModels] = useState<ChatModelInfo[]>([])
  const [selectedModel, setSelectedModel] = useState<string | null>(null)
  const [modelsLoading, setModelsLoading] = useState(false)

  // UI panels
  const [showContextPanel, setShowContextPanel] = useState(true)
  const [steeringDocs, setSteeringDocs] = useState<string[]>([])
  const [showAgentLogInChat, setShowAgentLogInChat] = useState(true)

  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingContent])

  const fetchModels = async () => {
    setModelsLoading(true)
    try {
      const url = `${API_BASE_URL}/chat/models`
      const res = await fetchWithLocalhostFallback(url, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error(`Failed to load models (${res.status})`)
      const data: ChatModelsResponse = await res.json()
      setModels(data.models)
      const defaultModel = data.defaults?.chat
      if (!selectedModel && defaultModel) setSelectedModel(defaultModel)
    } finally {
      setModelsLoading(false)
    }
  }

  const createThread = async () => {
    const url = `${API_BASE_URL}/repositories/${repositoryId}/chat/threads`
    const response = await fetchWithLocalhostFallback(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        title: 'Chat about code',
        context_file: contextFile,
        model: selectedModel,
      }),
    })
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      throw new Error(`Failed to create thread (${response.status}): ${text}`)
    }
    const data = await response.json()
    return data.id as string
  }

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput('')
    setIsLoading(true)

    // Add user message immediately (styled bubble)
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
      meta: { type: 'user' },
    }
    setMessages(prev => [...prev, tempUserMsg])

    // Add a lightweight "thinking" event (UI only; not model chain-of-thought)
    const thinkingMsg: Message = {
      id: `thinking-${Date.now()}`,
      role: 'assistant',
      content: 'Thinking…',
      created_at: new Date().toISOString(),
      meta: { type: 'thinking', title: 'Thinking' },
    }
    if (showAgentLogInChat) setMessages(prev => [...prev, thinkingMsg])

    try {
      // Create thread if needed
      let currentThreadId = threadId
      if (!currentThreadId) {
        currentThreadId = await createThread()
        setThreadId(currentThreadId)
      }

      // Send message with streaming
      const url = `${API_BASE_URL}/chat/threads/${currentThreadId}/messages`
      const response = await fetchWithLocalhostFallback(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          content: userMessage,
          stream: true,
          model: selectedModel, // per-message override (optional)
          context: {
            ref,
            active_file: activeFile,
            open_files: openFiles,
            tree: { path: '', depth: 4 },
          },
        }),
      })

      if (!response.ok) throw new Error('Failed to send message')

      // Handle SSE streaming (structured events)
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let fullContent = ''

      // Minimal SSE parser (supports event + data lines)
      let buffer = ''
      let currentEvent: string | null = null
      let currentDataLines: string[] = []

      const flushEvent = () => {
        if (!currentEvent && currentDataLines.length === 0) return
        const dataStr = currentDataLines.join('\n')
        const eventName = currentEvent || 'message'
        currentEvent = null
        currentDataLines = []

        if (eventName === 'token') {
          try {
            const payload = JSON.parse(dataStr) as { delta?: string }
            const delta = payload.delta || ''
            fullContent += delta
            setStreamingContent(fullContent)
          } catch {
            // ignore malformed token payload
          }
          return
        }

        if (eventName === 'step') {
          try {
            const payload = JSON.parse(dataStr) as { title?: string; detail?: string }
            const ev: Message = {
              id: `step-${Date.now()}`,
              role: 'assistant',
              content: payload.title || 'Step',
              created_at: new Date().toISOString(),
              meta: { type: 'thinking', title: payload.title || 'Step', details: payload.detail },
            }
            if (showAgentLogInChat) setMessages(prev => [...prev, ev])
          } catch {
            // ignore
          }
          return
        }

        if (eventName === 'tool_call') {
          try {
            const payload = JSON.parse(dataStr) as { name?: string; args?: unknown }
            const ev: Message = {
              id: `tool-call-${Date.now()}`,
              role: 'assistant',
              content: payload.name ? `Calling ${payload.name}` : 'Tool call',
              created_at: new Date().toISOString(),
              meta: { type: 'tool', title: payload.name || 'tool_call', details: JSON.stringify(payload.args || {}) },
            }
            if (showAgentLogInChat) setMessages(prev => [...prev, ev])
          } catch {
            // ignore
          }
          return
        }

        if (eventName === 'tool_result') {
          try {
            const payload = JSON.parse(dataStr) as { name?: string; ok?: boolean; error?: string; result?: unknown }
            const preview = payload.result ? JSON.stringify(payload.result).slice(0, 800) : ''
            const ev: Message = {
              id: `tool-result-${Date.now()}`,
              role: 'assistant',
              content: payload.name ? `Result ${payload.name}` : 'Tool result',
              created_at: new Date().toISOString(),
              meta: {
                type: 'tool',
                title: `${payload.name || 'tool_result'} ${payload.ok ? 'ok' : 'error'}`,
                details: payload.ok ? preview : (payload.error || 'Unknown error'),
              },
            }
            if (showAgentLogInChat) setMessages(prev => [...prev, ev])
          } catch {
            // ignore
          }
          return
        }

        if (eventName === 'context_source') {
          try {
            const payload = JSON.parse(dataStr) as {
              source?: string
              status?: string
              detail?: string
              count?: number
            }
            const source = payload.source || 'unknown'
            const status = payload.status || 'unknown'

            // Build a human-readable title
            const sourceLabels: Record<string, string> = {
              rag: '🔍 Vector RAG',
              tree: '📁 Repo Tree',
              active_file: '📄 Active File',
              github_api: '🐙 GitHub API',
            }
            const statusIcons: Record<string, string> = {
              found: '✓',
              empty: '∅',
              error: '✗',
              searching: '…',
              loading: '⟳',
            }

            const title = `${sourceLabels[source] || source} ${statusIcons[status] || status}`
            const detail = payload.detail || ''
            const countStr = payload.count !== undefined ? ` (${payload.count} items)` : ''

            const ev: Message = {
              id: `context-${source}-${Date.now()}`,
              role: 'assistant',
              content: `${title}${countStr}`,
              created_at: new Date().toISOString(),
              meta: {
                type: 'context_source',
                title,
                details: detail,
                source,
                status,
                count: payload.count,
              },
            }
            if (showAgentLogInChat) setMessages(prev => [...prev, ev])
          } catch {
            // ignore
          }
          return
        }

        if (eventName === 'done') {
          // Streaming complete
          setMessages(prev => [
            ...prev,
            {
              id: `assistant-${Date.now()}`,
              role: 'assistant',
              content: fullContent,
              created_at: new Date().toISOString(),
              meta: { type: 'assistant' },
            },
          ])
          setStreamingContent('')
          // no-op: agent log is now rendered inside chat messages
          return
        }

        if (eventName === 'error') {
          console.error('[chat] SSE error event', dataStr)
          setMessages(prev => [
            ...prev,
            {
              id: `error-${Date.now()}`,
              role: 'assistant',
              content: 'Sorry, something went wrong. Please try again.',
              created_at: new Date().toISOString(),
              meta: { type: 'assistant' },
            },
          ])
          setStreamingContent('')
          return
        }
      }

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          buffer += decoder.decode(value, { stream: true })
          const lines = buffer.split('\n')
          buffer = lines.pop() || ''

          for (const rawLine of lines) {
            const line = rawLine.replace(/\r$/, '')
            if (line === '') {
              flushEvent()
              continue
            }
            if (line.startsWith(':')) continue // comment/keepalive
            if (line.startsWith('event:')) {
              currentEvent = line.slice('event:'.length).trim()
              continue
            }
            if (line.startsWith('data:')) {
              currentDataLines.push(line.slice('data:'.length).trimStart())
              continue
            }
          }
        }

        // flush any trailing event
        flushEvent()
      }
    } catch (error) {
      console.error('Chat error:', error)
      // Show error message
      setMessages(prev => [
        ...prev,
        {
          id: `error-${Date.now()}`,
          role: 'assistant',
          content: 'Sorry, something went wrong. Please try again.',
          created_at: new Date().toISOString(),
          meta: { type: 'assistant' },
        },
      ])
    } finally {
      setIsLoading(false)
      setStreamingContent('')
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <div className={cn(
      'flex flex-col h-full bg-[#252526] border-l border-[#2b2b2b]',
      className
    )}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#2b2b2b] bg-[#252526]">
        <div />

        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowAgentLogInChat(v => !v)}
            className={cn(
              'px-2 py-1 rounded-sm transition-colors text-[#cccccc] text-[11px]',
              showAgentLogInChat ? 'bg-[#3c3c3c] hover:bg-[#454545]' : 'hover:bg-[#3c3c3c]'
            )}
            title="Toggle agent log in chat"
          >
            Log
          </button>

          <button
            onClick={() => setShowContextPanel(v => !v)}
            className="px-2 py-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc] text-[11px]"
            title="Toggle context panel"
          >
            Context
          </button>

          <button
            onClick={async () => {
              const next = !modelsOpen
              setModelsOpen(next)
              if (next && models.length === 0) await fetchModels()
            }}
            className="p-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc]"
            title="Manage models"
          >
            <Settings2 className="h-4 w-4" />
          </button>

          {onClose && (
            <button
              onClick={onClose}
              className="p-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc]"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>

      {/* Models popup */}
      {modelsOpen && (
        <div className="px-4 py-3 border-b border-[#2b2b2b] bg-[#2d2d2d] text-xs text-[#cccccc]">
          <div className="flex items-center justify-between mb-2">
            <span className="font-semibold">Model</span>
            <button
              onClick={() => setModelsOpen(false)}
              className="p-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc]"
              title="Close models"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          {modelsLoading ? (
            <div className="flex items-center gap-2 text-[#858585]">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading models...
            </div>
          ) : (
            <div className="space-y-1">
              {models.map(m => {
                const disabled = !m.available
                const selected = selectedModel === m.id
                return (
                  <button
                    key={m.id}
                    disabled={disabled}
                    onClick={() => setSelectedModel(m.id)}
                    className={cn(
                      'w-full text-left px-2 py-1 rounded-sm border border-transparent',
                      selected ? 'bg-[#094771] text-white' : 'hover:bg-[#3c3c3c]',
                      disabled && 'opacity-50 cursor-not-allowed hover:bg-transparent'
                    )}
                    title={disabled ? (m.reason_unavailable || 'Unavailable') : m.id}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate">{m.label}</span>
                      <span className="text-[10px] opacity-80">
                        {m.is_default ? 'default' : ''}
                      </span>
                    </div>
                    <div className="text-[10px] opacity-70 truncate">{m.id}</div>
                    {!m.available && m.reason_unavailable && (
                      <div className="text-[10px] text-[#d19a66] truncate">{m.reason_unavailable}</div>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Context + Steering panel */}
      {showContextPanel && (
        <div className="px-4 py-3 border-b border-[#2b2b2b] bg-[#1f1f1f] text-xs text-[#cccccc] space-y-2">
          <div className="flex items-center justify-between">
            <span className="font-semibold">Context</span>
            <button
              onClick={() => setShowContextPanel(false)}
              className="p-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc]"
              title="Close context"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>

          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <span className="opacity-80">ref</span>
              <span className="truncate text-[#9cdcfe]">{ref || '—'}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="opacity-80">active</span>
              <span className="truncate text-[#9cdcfe]">{activeFile || '—'}</span>
            </div>
            <div className="flex items-center justify-between gap-2">
              <span className="opacity-80">open</span>
              <span className="truncate text-[#9cdcfe]">{openFiles?.length ? `${openFiles.length} files` : '—'}</span>
            </div>
            {contextFile && (
              <div className="flex items-center justify-between gap-2">
                <span className="opacity-80">context</span>
                <span className="truncate text-[#9cdcfe]">{contextFile}</span>
              </div>
            )}
          </div>

          <div className="pt-2 border-t border-[#2b2b2b]">
            <div className="flex items-center justify-between">
              <span className="font-semibold">Steering used</span>
              <button
                onClick={() => setSteeringDocs([])}
                className="text-[10px] opacity-70 hover:opacity-100"
                title="Clear (UI only)"
              >
                clear
              </button>
            </div>
            {steeringDocs.length === 0 ? (
              <div className="text-[11px] text-[#858585]">No steering docs reported yet.</div>
            ) : (
              <ul className="mt-1 space-y-1">
                {steeringDocs.map((d) => (
                  <li key={d} className="truncate text-[#9cdcfe]">{d}</li>
                ))}
              </ul>
            )}
          </div>

        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 font-sans">
        {messages.length === 0 && !streamingContent && (
          <div className="text-center py-8 text-[#858585]">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Ask questions about your code</p>
            <p className="text-xs mt-1 text-[#666666]">I have context from your repository</p>
          </div>
        )}

        {messages.map((message) => {
          const isUser = message.role === 'user'
          const isTool = message.meta?.type === 'tool'
          const isThinking = message.meta?.type === 'thinking'
          const isContextSource = message.meta?.type === 'context_source'

          if (!showAgentLogInChat && (isTool || isThinking || isContextSource)) return null

          // Context source events get special compact styling
          if (isContextSource) {
            const status = message.meta?.status || 'unknown'
            const statusColors: Record<string, string> = {
              found: 'text-[#4ec9b0]',      // green
              empty: 'text-[#d19a66]',      // orange
              error: 'text-[#f44747]',      // red
              searching: 'text-[#569cd6]', // blue
              loading: 'text-[#569cd6]',   // blue
            }

            return (
              <div key={message.id} className="flex justify-start">
                <div className="max-w-[92%] rounded px-2 py-1 text-xs bg-[#1a1a1a] border border-[#333] text-[#888]">
                  <span className={statusColors[status] || 'text-[#888]'}>
                    {message.content}
                  </span>
                  {message.meta?.details && (
                    <span className="ml-2 opacity-60">{message.meta.details}</span>
                  )}
                </div>
              </div>
            )
          }

          return (
            <div key={message.id} className={cn('flex', isUser ? 'justify-end' : 'justify-start')}>
              <div
                className={cn(
                  'max-w-[92%] rounded-lg px-3 py-2 text-sm leading-relaxed break-words border',
                  isUser
                    ? 'bg-[#0e639c]/20 border-[#0e639c]/40 text-[#d7eaff] whitespace-pre-wrap'
                    : isTool
                      ? 'bg-[#2d2d2d] border-[#3c3c3c] text-[#cccccc] whitespace-pre-wrap'
                      : isThinking
                        ? 'bg-[#232323] border-[#3c3c3c] text-[#cccccc] whitespace-pre-wrap'
                        : 'bg-[#1e1e1e] border-[#2b2b2b] text-[#cccccc]'
                )}
              >
                <div className="text-[10px] uppercase tracking-wide opacity-70 mb-1">
                  {isUser ? 'You' : (message.meta?.title || 'N9R')}
                </div>
                {/* Render markdown for assistant messages, plain text for others */}
                {isUser || isTool || isThinking ? (
                  message.content
                ) : (
                  <MarkdownContent>{message.content}</MarkdownContent>
                )}
                {message.meta?.details && (
                  <div className="mt-2 text-[11px] opacity-70 whitespace-pre-wrap break-words">
                    {message.meta.details}
                  </div>
                )}
              </div>
            </div>
          )
        })}

        {/* Streaming message */}
        {streamingContent && (
          <div className="flex justify-start">
            <div className="max-w-[92%] rounded-lg px-3 py-2 text-sm leading-relaxed break-words border bg-[#1e1e1e] border-[#2b2b2b] text-[#cccccc]">
              <div className="text-[10px] uppercase tracking-wide opacity-70 mb-1">N9R</div>
              <MarkdownContent>{streamingContent}</MarkdownContent>
              <span className="inline-block w-1.5 h-4 bg-[#0e639c] animate-pulse ml-1 align-middle" />
            </div>
          </div>
        )}

        {/* Loading indicator */}
        {isLoading && !streamingContent && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-[#007fd4] flex-shrink-0" />
              <span className="font-bold text-xs text-[#cccccc]">N9R</span>
            </div>
            <div className="pl-6">
              <Loader2 className="h-4 w-4 animate-spin text-[#cccccc]" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-3 border-t border-[#2b2b2b] bg-[#252526]">
        <div className="group bg-[#1e1e1e] border border-[#3c3c3c] rounded-lg p-2 flex flex-col gap-1 focus-within:border-[#007fd4] transition-colors">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask anything (⌘L), @ to mention, / for workflows"
            rows={1}
            className="w-full bg-transparent border-none px-2 py-1.5 text-sm text-[#cccccc] resize-none focus:outline-none placeholder-[#6e7681]"
            disabled={isLoading}
            style={{ minHeight: '24px', maxHeight: '200px' }}
          />
          <div className="flex items-center justify-between px-1 pt-1">
            <div className="flex items-center gap-2">
              <button className="p-1 rounded-sm hover:bg-[#3c3c3c] text-[#cccccc] transition-colors" title="Add Context">
                <Plus className="h-3.5 w-3.5 opacity-70" />
              </button>
            </div>
            <Button
              onClick={sendMessage}
              disabled={!input.trim() || isLoading}
              size="sm"
              className="h-6 w-6 p-0 rounded bg-[#0e639c] hover:bg-[#1177bb] text-white flex items-center justify-center disabled:opacity-50 shadow-none border-none"
            >
              <Send className="h-3 w-3" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
