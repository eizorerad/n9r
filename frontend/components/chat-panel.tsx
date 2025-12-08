'use client'

import { useState, useRef, useEffect } from 'react'
import { Send, X, MessageSquare, Loader2, Plus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

interface ChatPanelProps {
  repositoryId: string
  threadId?: string
  contextFile?: string
  className?: string
  onClose?: () => void
}

export function ChatPanel({
  repositoryId,
  threadId: initialThreadId,
  contextFile,
  className,
  onClose,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [threadId, setThreadId] = useState(initialThreadId)
  const [streamingContent, setStreamingContent] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingContent])

  const createThread = async () => {
    const response = await fetch(`/api/repositories/${repositoryId}/chat/threads`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: 'Chat about code',
        context_file: contextFile,
      }),
    })
    const data = await response.json()
    return data.id
  }

  const sendMessage = async () => {
    if (!input.trim() || isLoading) return

    const userMessage = input.trim()
    setInput('')
    setIsLoading(true)

    // Add user message immediately
    const tempUserMsg: Message = {
      id: `temp-${Date.now()}`,
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, tempUserMsg])

    try {
      // Create thread if needed
      let currentThreadId = threadId
      if (!currentThreadId) {
        currentThreadId = await createThread()
        setThreadId(currentThreadId)
      }

      // Send message with streaming
      const response = await fetch(`/api/chat/threads/${currentThreadId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          content: userMessage,
          stream: true,
        }),
      })

      if (!response.ok) throw new Error('Failed to send message')

      // Handle SSE streaming
      const reader = response.body?.getReader()
      const decoder = new TextDecoder()
      let fullContent = ''

      if (reader) {
        while (true) {
          const { done, value } = await reader.read()
          if (done) break

          const chunk = decoder.decode(value)
          const lines = chunk.split('\n')

          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6)
              if (data === '[DONE]') {
                // Streaming complete
                setMessages(prev => [
                  ...prev,
                  {
                    id: `assistant-${Date.now()}`,
                    role: 'assistant',
                    content: fullContent,
                    created_at: new Date().toISOString(),
                  },
                ])
                setStreamingContent('')
              } else {
                fullContent += data
                setStreamingContent(fullContent)
              }
            }
          }
        }
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
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2b2b2b] bg-[#252526]">
        <div className="flex items-center gap-2">
          <MessageSquare className="h-4 w-4 text-[#cccccc]" />
          <span className="font-medium text-xs font-sans text-[#cccccc] uppercase tracking-wide">Ask AI</span>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 hover:bg-[#3c3c3c] rounded-sm transition-colors text-[#cccccc]"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Context indicator */}
      {contextFile && (
        <div className="px-4 py-2 bg-[#2d2d2d] border-b border-[#2b2b2b] text-xs text-[#cccccc]">
          Context: <span className="text-[#9cdcfe]">{contextFile}</span>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 font-sans">
        {messages.length === 0 && !streamingContent && (
          <div className="text-center py-8 text-[#858585]">
            <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p className="text-sm">Ask questions about your code</p>
            <p className="text-xs mt-1 text-[#666666]">I have context from your repository</p>
          </div>
        )}

        {messages.map((message) => (
          <div key={message.id} className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              {message.role === 'user' ? (
                <>
                  <div className="h-4 w-4 rounded-sm bg-[#0e639c] flex items-center justify-center text-[10px] text-white font-bold flex-shrink-0">
                    U
                  </div>
                  <span className="font-bold text-xs text-[#cccccc]">You</span>
                </>
              ) : (
                <>
                  <MessageSquare className="h-4 w-4 text-[#007fd4] flex-shrink-0" />
                  <span className="font-bold text-xs text-[#cccccc]">N9R</span>
                </>
              )}
            </div>
            <div className="pl-6 text-sm text-[#cccccc] leading-relaxed break-words whitespace-pre-wrap">
              {message.content}
            </div>
          </div>
        ))}

        {/* Streaming message */}
        {streamingContent && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2">
              <MessageSquare className="h-4 w-4 text-[#007fd4] flex-shrink-0" />
              <span className="font-bold text-xs text-[#cccccc]">N9R</span>
            </div>
            <div className="pl-6 text-sm text-[#cccccc] leading-relaxed break-words whitespace-pre-wrap">
              {streamingContent}
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
