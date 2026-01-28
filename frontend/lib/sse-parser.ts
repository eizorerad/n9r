/**
 * SSE Parser Utility
 * 
 * Implements proper Server-Sent Events parsing according to the SSE specification:
 * https://html.spec.whatwg.org/multipage/server-sent-events.html
 * 
 * Key features:
 * - Parses by event boundaries (\n\n) not individual lines
 * - Supports multiline data: fields (concatenated with \n)
 * - Ignores comment lines starting with :
 * - Handles event:, data:, id:, retry: fields
 */

export interface SSEEvent {
  /** Event type (from 'event:' field), defaults to 'message' */
  type: string
  /** Event data (from 'data:' field(s)), multiline data joined with \n */
  data: string
  /** Last event ID (from 'id:' field) */
  id?: string
  /** Reconnection time in ms (from 'retry:' field) */
  retry?: number
}

export interface ParseResult {
  /** Fully parsed events */
  events: SSEEvent[]
  /** Remaining buffer (incomplete event data) */
  remainingBuffer: string
}

/**
 * Parse a single SSE event block (text between \n\n boundaries)
 * Returns null for comment-only blocks or empty blocks
 */
function parseEventBlock(block: string): SSEEvent | null {
  const lines = block.split('\n')
  
  let eventType = 'message'
  const dataLines: string[] = []
  let id: string | undefined
  let retry: number | undefined
  let hasData = false
  
  for (const line of lines) {
    // Empty line within block - shouldn't happen after proper splitting, but handle gracefully
    if (line === '') continue
    
    // Comment line - ignore (used for keepalive)
    if (line.startsWith(':')) continue
    
    // Find the field name and value
    const colonIndex = line.indexOf(':')
    
    if (colonIndex === -1) {
      // Line with no colon - treat as field name with empty value
      // Per spec: "If the line is not empty but does not contain a U+003A COLON character"
      // "use the whole line as the field name, and the empty string as the field value"
      continue
    }
    
    const fieldName = line.slice(0, colonIndex)
    // Per spec: if there's a space after the colon, skip it
    let fieldValue = line.slice(colonIndex + 1)
    if (fieldValue.startsWith(' ')) {
      fieldValue = fieldValue.slice(1)
    }
    
    switch (fieldName) {
      case 'event':
        eventType = fieldValue
        break
      case 'data':
        dataLines.push(fieldValue)
        hasData = true
        break
      case 'id':
        // Per spec: if id contains null, ignore
        if (!fieldValue.includes('\0')) {
          id = fieldValue
        }
        break
      case 'retry':
        // Per spec: if value consists of ASCII digits only, set retry
        if (/^\d+$/.test(fieldValue)) {
          retry = parseInt(fieldValue, 10)
        }
        break
      // Unknown fields are ignored per spec
    }
  }
  
  // If no data field was present, don't dispatch an event
  if (!hasData) {
    return null
  }
  
  // Per spec: join multiple data lines with \n
  const data = dataLines.join('\n')
  
  return {
    type: eventType,
    data,
    ...(id !== undefined && { id }),
    ...(retry !== undefined && { retry }),
  }
}

/**
 * Parse SSE events from a chunk of text, maintaining a buffer for incomplete events.
 * 
 * @param chunk - New chunk of text received from the stream
 * @param buffer - Existing buffer from previous chunks (incomplete event data)
 * @returns Object containing parsed events and remaining buffer
 * 
 * @example
 * ```ts
 * let buffer = ''
 * 
 * // In your stream reading loop:
 * const { events, remainingBuffer } = parseSSEEvents(chunk, buffer)
 * buffer = remainingBuffer
 * 
 * for (const event of events) {
 *   if (event.type === 'message') {
 *     const data = JSON.parse(event.data)
 *     // Handle the event
 *   }
 * }
 * ```
 */
export function parseSSEEvents(chunk: string, buffer: string): ParseResult {
  const combined = buffer + chunk
  const events: SSEEvent[] = []
  
  // Split by event boundaries (double newline)
  // Handle both \n\n and \r\n\r\n
  const parts = combined.split(/\r?\n\r?\n/)
  
  // The last part might be incomplete (no trailing \n\n yet)
  const remainingBuffer = parts.pop() || ''
  
  // Parse each complete event block
  for (const block of parts) {
    if (block.trim() === '') continue
    
    const event = parseEventBlock(block)
    if (event) {
      events.push(event)
    }
  }
  
  return {
    events,
    remainingBuffer,
  }
}

/**
 * Check if a line is a comment (keepalive)
 * Useful for quick filtering before full parsing
 */
export function isComment(line: string): boolean {
  return line.startsWith(':')
}

/**
 * Type guard to check if parsed JSON matches ProgressUpdate shape
 */
export function isProgressUpdate(data: unknown): data is {
  analysis_id: string
  stage: string
  progress: number
  message: string | null
  status: string
  vci_score?: number
  commit_sha?: string
} {
  if (typeof data !== 'object' || data === null) return false
  const obj = data as Record<string, unknown>
  return (
    typeof obj.analysis_id === 'string' &&
    typeof obj.stage === 'string' &&
    typeof obj.progress === 'number' &&
    typeof obj.status === 'string'
  )
}

/**
 * Safely parse JSON data from an SSE event
 * Returns null if parsing fails, with optional error logging
 */
export function parseEventData<T>(
  event: SSEEvent,
  options?: { logErrors?: boolean; context?: string }
): T | null {
  try {
    return JSON.parse(event.data) as T
  } catch (error) {
    if (options?.logErrors) {
      const context = options.context ? `[${options.context}]` : ''
      console.warn(`${context} Failed to parse SSE event data:`, {
        eventType: event.type,
        dataPreview: event.data.slice(0, 100),
        error: error instanceof Error ? error.message : 'Unknown error',
      })
    }
    return null
  }
}
