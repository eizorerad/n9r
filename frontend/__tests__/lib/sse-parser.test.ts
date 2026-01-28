/**
 * Unit Tests for SSE Parser Utility
 * 
 * **Feature: Problem 7 - Frontend reliability**
 * **Validates: E6 - SSE parser tests**
 * 
 * Tests the SSE parser implementation according to the SSE specification:
 * https://html.spec.whatwg.org/multipage/server-sent-events.html
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import {
  parseSSEEvents,
  parseEventData,
  isComment,
  isProgressUpdate,
  type SSEEvent,
} from '@/lib/sse-parser'

describe('SSE Parser', () => {
  describe('parseSSEEvents', () => {
    describe('event boundary parsing (\\n\\n)', () => {
      it('should parse single complete event', () => {
        const chunk = 'data: {"status":"running"}\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].type).toBe('message')
        expect(events[0].data).toBe('{"status":"running"}')
        expect(remainingBuffer).toBe('')
      })

      it('should parse multiple complete events', () => {
        const chunk = 'data: {"id":1}\n\ndata: {"id":2}\n\ndata: {"id":3}\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(3)
        expect(events[0].data).toBe('{"id":1}')
        expect(events[1].data).toBe('{"id":2}')
        expect(events[2].data).toBe('{"id":3}')
        expect(remainingBuffer).toBe('')
      })

      it('should handle CRLF line endings (\\r\\n\\r\\n)', () => {
        const chunk = 'data: {"status":"running"}\r\n\r\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('{"status":"running"}')
        expect(remainingBuffer).toBe('')
      })

      it('should handle mixed line endings', () => {
        const chunk = 'data: first\n\ndata: second\r\n\r\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(2)
        expect(events[0].data).toBe('first')
        expect(events[1].data).toBe('second')
      })
    })

    describe('incomplete event buffering', () => {
      it('should buffer incomplete event without trailing \\n\\n', () => {
        const chunk = 'data: {"status":"running"}'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(0)
        expect(remainingBuffer).toBe('data: {"status":"running"}')
      })

      it('should combine buffer with new chunk', () => {
        const buffer = 'data: {"status":'
        const chunk = '"running"}\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, buffer)

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('{"status":"running"}')
        expect(remainingBuffer).toBe('')
      })

      it('should handle partial event across multiple chunks', () => {
        // First chunk - incomplete
        const result1 = parseSSEEvents('data: {"id":1', '')
        expect(result1.events).toHaveLength(0)
        expect(result1.remainingBuffer).toBe('data: {"id":1')

        // Second chunk - still incomplete
        const result2 = parseSSEEvents(',"name":"test"', result1.remainingBuffer)
        expect(result2.events).toHaveLength(0)
        expect(result2.remainingBuffer).toBe('data: {"id":1,"name":"test"')

        // Third chunk - completes the event
        const result3 = parseSSEEvents('}\n\n', result2.remainingBuffer)
        expect(result3.events).toHaveLength(1)
        expect(result3.events[0].data).toBe('{"id":1,"name":"test"}')
        expect(result3.remainingBuffer).toBe('')
      })

      it('should handle complete event followed by incomplete event', () => {
        const chunk = 'data: complete\n\ndata: incomplete'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('complete')
        expect(remainingBuffer).toBe('data: incomplete')
      })
    })

    describe('multiline data: field concatenation', () => {
      it('should concatenate multiple data: lines with newline', () => {
        const chunk = 'data: line1\ndata: line2\ndata: line3\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('line1\nline2\nline3')
        expect(remainingBuffer).toBe('')
      })

      it('should handle multiline JSON data', () => {
        const chunk = 'data: {\ndata:   "key": "value"\ndata: }\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('{\n  "key": "value"\n}')
      })

      it('should handle empty data: lines', () => {
        const chunk = 'data: first\ndata:\ndata: third\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('first\n\nthird')
      })
    })

    describe('comment (: prefix) ignoring', () => {
      it('should ignore comment-only lines', () => {
        const chunk = ': this is a comment\ndata: actual data\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('actual data')
      })

      it('should ignore keepalive comments', () => {
        const chunk = ': keepalive\n\ndata: real event\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        // Comment-only block should not produce an event
        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('real event')
      })

      it('should ignore multiple comments in event', () => {
        const chunk = ': comment 1\n: comment 2\ndata: value\n: comment 3\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('value')
      })

      it('should not produce event for comment-only block', () => {
        const chunk = ': just a comment\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(0)
        expect(remainingBuffer).toBe('')
      })
    })

    describe('event: field parsing', () => {
      it('should parse event type from event: field', () => {
        const chunk = 'event: progress\ndata: {"value":50}\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].type).toBe('progress')
        expect(events[0].data).toBe('{"value":50}')
      })

      it('should default to "message" when no event: field', () => {
        const chunk = 'data: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].type).toBe('message')
      })

      it('should use last event: field if multiple present', () => {
        const chunk = 'event: first\nevent: second\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].type).toBe('second')
      })
    })

    describe('id: field parsing', () => {
      it('should parse id from id: field', () => {
        const chunk = 'id: 123\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].id).toBe('123')
      })

      it('should not include id if not present', () => {
        const chunk = 'data: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].id).toBeUndefined()
      })

      it('should ignore id containing null character', () => {
        const chunk = 'id: test\0value\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].id).toBeUndefined()
      })
    })

    describe('retry: field parsing', () => {
      it('should parse retry time from retry: field', () => {
        const chunk = 'retry: 5000\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].retry).toBe(5000)
      })

      it('should not include retry if not present', () => {
        const chunk = 'data: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].retry).toBeUndefined()
      })

      it('should ignore non-numeric retry values', () => {
        const chunk = 'retry: abc\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].retry).toBeUndefined()
      })

      it('should ignore retry with mixed characters', () => {
        const chunk = 'retry: 500ms\ndata: test\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].retry).toBeUndefined()
      })
    })

    describe('empty data handling', () => {
      it('should not produce event when no data: field present', () => {
        const chunk = 'event: ping\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(0)
      })

      it('should produce event with empty string for data:', () => {
        const chunk = 'data:\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('')
      })

      it('should handle empty block', () => {
        const chunk = '\n\n'
        const { events, remainingBuffer } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(0)
        expect(remainingBuffer).toBe('')
      })
    })

    describe('field value handling', () => {
      it('should strip single leading space from field value', () => {
        const chunk = 'data: value with space\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].data).toBe('value with space')
      })

      it('should not strip multiple leading spaces', () => {
        const chunk = 'data:  two spaces\n\n'
        const { events } = parseSSEEvents(chunk, '')

        // Per spec: only first space after colon is stripped
        expect(events[0].data).toBe(' two spaces')
      })

      it('should handle field with no space after colon', () => {
        const chunk = 'data:no-space\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events[0].data).toBe('no-space')
      })

      it('should ignore unknown fields', () => {
        const chunk = 'custom: ignored\ndata: kept\nunknown: also ignored\n\n'
        const { events } = parseSSEEvents(chunk, '')

        expect(events).toHaveLength(1)
        expect(events[0].data).toBe('kept')
      })
    })
  })

  describe('parseEventData', () => {
    it('should parse valid JSON data', () => {
      const event: SSEEvent = {
        type: 'message',
        data: '{"status":"running","progress":50}',
      }

      const result = parseEventData<{ status: string; progress: number }>(event)

      expect(result).toEqual({ status: 'running', progress: 50 })
    })

    it('should return null for invalid JSON', () => {
      const event: SSEEvent = {
        type: 'message',
        data: 'not valid json',
      }

      const result = parseEventData(event)

      expect(result).toBeNull()
    })

    it('should return null for empty data', () => {
      const event: SSEEvent = {
        type: 'message',
        data: '',
      }

      const result = parseEventData(event)

      expect(result).toBeNull()
    })

    it('should log errors when logErrors option is true', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const event: SSEEvent = {
        type: 'message',
        data: 'invalid json',
      }

      parseEventData(event, { logErrors: true })

      expect(consoleSpy).toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('should include context in error log when provided', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const event: SSEEvent = {
        type: 'message',
        data: 'invalid',
      }

      parseEventData(event, { logErrors: true, context: 'TestContext' })

      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('[TestContext]'),
        expect.any(Object)
      )
      consoleSpy.mockRestore()
    })

    it('should not log errors when logErrors option is false', () => {
      const consoleSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
      const event: SSEEvent = {
        type: 'message',
        data: 'invalid',
      }

      parseEventData(event, { logErrors: false })

      expect(consoleSpy).not.toHaveBeenCalled()
      consoleSpy.mockRestore()
    })

    it('should handle nested JSON objects', () => {
      const event: SSEEvent = {
        type: 'message',
        data: '{"outer":{"inner":{"value":42}}}',
      }

      const result = parseEventData<{ outer: { inner: { value: number } } }>(event)

      expect(result?.outer.inner.value).toBe(42)
    })

    it('should handle JSON arrays', () => {
      const event: SSEEvent = {
        type: 'message',
        data: '[1,2,3]',
      }

      const result = parseEventData<number[]>(event)

      expect(result).toEqual([1, 2, 3])
    })
  })

  describe('isComment', () => {
    it('should return true for lines starting with :', () => {
      expect(isComment(': keepalive')).toBe(true)
      expect(isComment(':')).toBe(true)
      expect(isComment(': ')).toBe(true)
    })

    it('should return false for non-comment lines', () => {
      expect(isComment('data: value')).toBe(false)
      expect(isComment('event: type')).toBe(false)
      expect(isComment('')).toBe(false)
      expect(isComment(' : not a comment')).toBe(false)
    })
  })

  describe('isProgressUpdate', () => {
    it('should return true for valid progress update', () => {
      const data = {
        analysis_id: 'test-id',
        stage: 'analyzing',
        progress: 50,
        message: 'Processing...',
        status: 'running',
      }

      expect(isProgressUpdate(data)).toBe(true)
    })

    it('should return true with optional fields', () => {
      const data = {
        analysis_id: 'test-id',
        stage: 'completed',
        progress: 100,
        message: null,
        status: 'completed',
        vci_score: 85,
        commit_sha: 'abc123',
      }

      expect(isProgressUpdate(data)).toBe(true)
    })

    it('should return false for null', () => {
      expect(isProgressUpdate(null)).toBe(false)
    })

    it('should return false for non-object', () => {
      expect(isProgressUpdate('string')).toBe(false)
      expect(isProgressUpdate(123)).toBe(false)
      expect(isProgressUpdate(undefined)).toBe(false)
    })

    it('should return false for missing required fields', () => {
      expect(isProgressUpdate({ analysis_id: 'test' })).toBe(false)
      expect(isProgressUpdate({ stage: 'test', progress: 50 })).toBe(false)
      expect(isProgressUpdate({ analysis_id: 'test', stage: 'test', progress: 50 })).toBe(false)
    })

    it('should return false for wrong field types', () => {
      expect(isProgressUpdate({
        analysis_id: 123, // should be string
        stage: 'test',
        progress: 50,
        status: 'running',
      })).toBe(false)

      expect(isProgressUpdate({
        analysis_id: 'test',
        stage: 'test',
        progress: '50', // should be number
        status: 'running',
      })).toBe(false)
    })
  })

  describe('edge cases and real-world scenarios', () => {
    it('should handle typical backend progress event', () => {
      const chunk = 'data: {"analysis_id":"uuid-123","stage":"cloning","progress":10,"message":"Cloning repository...","status":"running"}\n\n'
      const { events } = parseSSEEvents(chunk, '')

      expect(events).toHaveLength(1)
      const data = parseEventData<{
        analysis_id: string
        stage: string
        progress: number
        message: string
        status: string
      }>(events[0])

      expect(data).not.toBeNull()
      expect(data?.analysis_id).toBe('uuid-123')
      expect(data?.stage).toBe('cloning')
      expect(data?.progress).toBe(10)
      expect(isProgressUpdate(data)).toBe(true)
    })

    it('should handle keepalive followed by data event', () => {
      const chunk = ': keepalive\n\ndata: {"status":"running"}\n\n'
      const { events } = parseSSEEvents(chunk, '')

      expect(events).toHaveLength(1)
      expect(events[0].data).toBe('{"status":"running"}')
    })

    it('should handle rapid succession of events', () => {
      const events_data = Array.from({ length: 100 }, (_, i) => 
        `data: {"progress":${i}}\n\n`
      ).join('')
      
      const { events, remainingBuffer } = parseSSEEvents(events_data, '')

      expect(events).toHaveLength(100)
      expect(remainingBuffer).toBe('')
      events.forEach((event, i) => {
        expect(parseEventData<{ progress: number }>(event)?.progress).toBe(i)
      })
    })

    it('should handle chunked delivery of single event', () => {
      const fullEvent = 'data: {"analysis_id":"test","stage":"analyzing","progress":50,"message":"Working...","status":"running"}\n\n'
      
      // Simulate chunked delivery
      let buffer = ''
      const chunkSize = 10
      let events: SSEEvent[] = []

      for (let i = 0; i < fullEvent.length; i += chunkSize) {
        const chunk = fullEvent.slice(i, i + chunkSize)
        const result = parseSSEEvents(chunk, buffer)
        events = events.concat(result.events)
        buffer = result.remainingBuffer
      }

      expect(events).toHaveLength(1)
      expect(buffer).toBe('')
      expect(isProgressUpdate(parseEventData(events[0]))).toBe(true)
    })

    it('should handle event with all fields', () => {
      const chunk = 'event: progress\nid: 42\nretry: 3000\ndata: {"value":100}\n\n'
      const { events } = parseSSEEvents(chunk, '')

      expect(events).toHaveLength(1)
      expect(events[0].type).toBe('progress')
      expect(events[0].id).toBe('42')
      expect(events[0].retry).toBe(3000)
      expect(events[0].data).toBe('{"value":100}')
    })

    it('should handle Unicode in data', () => {
      const chunk = 'data: {"message":"Анализ завершён 🎉"}\n\n'
      const { events } = parseSSEEvents(chunk, '')

      expect(events).toHaveLength(1)
      const data = parseEventData<{ message: string }>(events[0])
      expect(data?.message).toBe('Анализ завершён 🎉')
    })

    it('should handle special characters in JSON', () => {
      const chunk = 'data: {"path":"C:\\\\Users\\\\test","url":"https://example.com?a=1&b=2"}\n\n'
      const { events } = parseSSEEvents(chunk, '')

      expect(events).toHaveLength(1)
      const data = parseEventData<{ path: string; url: string }>(events[0])
      expect(data?.path).toBe('C:\\Users\\test')
      expect(data?.url).toBe('https://example.com?a=1&b=2')
    })
  })
})
