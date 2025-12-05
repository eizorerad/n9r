/**
 * Property-Based Tests for AnalysisProgressStore
 * 
 * **Feature: ai-scan-progress-fix, Property 9: Progress Store Task Type**
 * **Validates: Requirements 3.1**
 */

import { describe, it, expect, beforeEach } from 'vitest'
import * as fc from 'fast-check'
import { 
  useAnalysisProgressStore, 
  getAnalysisTaskId, 
  getEmbeddingsTaskId, 
  getAIScanTaskId,
  type ProgressTask 
} from '@/lib/stores/analysis-progress-store'

// Arbitrary generators for test data
const repositoryIdArb = fc.uuid()
const taskStatusArb = fc.constantFrom('idle', 'pending', 'running', 'completed', 'failed') as fc.Arbitrary<'idle' | 'pending' | 'running' | 'completed' | 'failed'>
const progressArb = fc.integer({ min: 0, max: 100 })
const stageArb = fc.constantFrom('initializing', 'cloning', 'generating_view', 'scanning', 'merging', 'investigating', 'completed')
const messageArb = fc.option(fc.string({ minLength: 1, maxLength: 100 }), { nil: null })
const repositoryNameArb = fc.option(fc.string({ minLength: 1, maxLength: 50 }), { nil: undefined })

describe('AnalysisProgressStore - Property 9: Progress Store Task Type', () => {
  beforeEach(() => {
    // Reset the store before each test by setting tasks to empty object
    useAnalysisProgressStore.setState({ tasks: {}, minimized: false })
  })

  /**
   * **Feature: ai-scan-progress-fix, Property 9: Progress Store Task Type**
   * **Validates: Requirements 3.1**
   * 
   * Property: For any AI scan task added to the frontend progress store, 
   * the task type SHALL be "ai_scan" and the task ID SHALL follow the 
   * pattern "ai_scan-{repositoryId}".
   */
  it('should generate correct AI scan task ID following pattern ai_scan-{repositoryId}', () => {
    fc.assert(
      fc.property(repositoryIdArb, (repositoryId) => {
        const taskId = getAIScanTaskId(repositoryId)
        
        // Task ID MUST follow the pattern "ai_scan-{repositoryId}"
        expect(taskId).toBe(`ai_scan-${repositoryId}`)
        
        // Task ID MUST start with "ai_scan-"
        expect(taskId.startsWith('ai_scan-')).toBe(true)
        
        // Task ID MUST contain the repository ID
        expect(taskId.includes(repositoryId)).toBe(true)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: AI scan tasks added to the store SHALL have type "ai_scan"
   * and maintain the correct task ID pattern.
   */
  it('should store AI scan tasks with correct type and ID', () => {
    fc.assert(
      fc.property(
        repositoryIdArb,
        taskStatusArb,
        progressArb,
        stageArb,
        messageArb,
        repositoryNameArb,
        (repositoryId, status, progress, stage, message, repositoryName) => {
          // Reset store at start of each iteration
          useAnalysisProgressStore.setState({ tasks: {}, minimized: false })
          
          const taskId = getAIScanTaskId(repositoryId)
          
          // Add an AI scan task
          const task: Omit<ProgressTask, 'startedAt'> = {
            id: taskId,
            type: 'ai_scan',
            repositoryId,
            repositoryName,
            status,
            progress,
            stage,
            message,
          }
          
          useAnalysisProgressStore.getState().addTask(task)
          
          // Verify the task was stored correctly (get fresh state)
          const storedTask = useAnalysisProgressStore.getState().tasks[taskId]
          expect(storedTask).toBeDefined()
          expect(storedTask.type).toBe('ai_scan')
          expect(storedTask.id).toBe(`ai_scan-${repositoryId}`)
          expect(storedTask.repositoryId).toBe(repositoryId)
          expect(storedTask.status).toBe(status)
          expect(storedTask.progress).toBe(progress)
        }
      ),
      { numRuns: 100 }
    )
  })

  /**
   * Property: All three task type helper functions SHALL generate unique
   * task IDs for the same repository ID.
   */
  it('should generate unique task IDs for different task types', () => {
    fc.assert(
      fc.property(repositoryIdArb, (repositoryId) => {
        const analysisTaskId = getAnalysisTaskId(repositoryId)
        const embeddingsTaskId = getEmbeddingsTaskId(repositoryId)
        const aiScanTaskId = getAIScanTaskId(repositoryId)
        
        // All task IDs MUST be different for the same repository
        expect(analysisTaskId).not.toBe(embeddingsTaskId)
        expect(analysisTaskId).not.toBe(aiScanTaskId)
        expect(embeddingsTaskId).not.toBe(aiScanTaskId)
        
        // Each task ID MUST follow its respective pattern
        expect(analysisTaskId).toBe(`analysis-${repositoryId}`)
        expect(embeddingsTaskId).toBe(`embeddings-${repositoryId}`)
        expect(aiScanTaskId).toBe(`ai_scan-${repositoryId}`)
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: The progress store SHALL support all three task types
   * (analysis, embeddings, ai_scan) simultaneously.
   */
  it('should support all three task types simultaneously', () => {
    fc.assert(
      fc.property(repositoryIdArb, (repositoryId) => {
        // Reset store at start of each iteration
        useAnalysisProgressStore.setState({ tasks: {}, minimized: false })
        
        const analysisTaskId = getAnalysisTaskId(repositoryId)
        const embeddingsTaskId = getEmbeddingsTaskId(repositoryId)
        const aiScanTaskId = getAIScanTaskId(repositoryId)
        
        // Add all three task types
        useAnalysisProgressStore.getState().addTask({
          id: analysisTaskId,
          type: 'analysis',
          repositoryId,
          status: 'running',
          progress: 50,
          stage: 'analyzing',
          message: null,
        })
        
        useAnalysisProgressStore.getState().addTask({
          id: embeddingsTaskId,
          type: 'embeddings',
          repositoryId,
          status: 'pending',
          progress: 0,
          stage: 'pending',
          message: null,
        })
        
        useAnalysisProgressStore.getState().addTask({
          id: aiScanTaskId,
          type: 'ai_scan',
          repositoryId,
          status: 'running',
          progress: 25,
          stage: 'scanning',
          message: 'Scanning files...',
        })
        
        // Get fresh state for assertions
        const state = useAnalysisProgressStore.getState()
        
        // All three tasks MUST exist in the store
        expect(state.hasTask(analysisTaskId)).toBe(true)
        expect(state.hasTask(embeddingsTaskId)).toBe(true)
        expect(state.hasTask(aiScanTaskId)).toBe(true)
        
        // Each task MUST have the correct type
        expect(state.tasks[analysisTaskId].type).toBe('analysis')
        expect(state.tasks[embeddingsTaskId].type).toBe('embeddings')
        expect(state.tasks[aiScanTaskId].type).toBe('ai_scan')
      }),
      { numRuns: 100 }
    )
  })

  /**
   * Property: AI scan tasks SHALL be included in getActiveTasks when
   * their status is 'pending' or 'running'.
   */
  it('should include AI scan tasks in active tasks when pending or running', () => {
    const activeStatusArb = fc.constantFrom('pending', 'running') as fc.Arbitrary<'pending' | 'running'>
    const inactiveStatusArb = fc.constantFrom('idle', 'completed', 'failed') as fc.Arbitrary<'idle' | 'completed' | 'failed'>
    
    fc.assert(
      fc.property(repositoryIdArb, activeStatusArb, (repositoryId, status) => {
        // Reset store at start of each iteration
        useAnalysisProgressStore.setState({ tasks: {}, minimized: false })
        
        const taskId = getAIScanTaskId(repositoryId)
        
        useAnalysisProgressStore.getState().addTask({
          id: taskId,
          type: 'ai_scan',
          repositoryId,
          status,
          progress: 50,
          stage: 'scanning',
          message: null,
        })
        
        const state = useAnalysisProgressStore.getState()
        const activeTasks = state.getActiveTasks()
        
        // AI scan task with pending/running status MUST be in active tasks
        expect(activeTasks.some(t => t.id === taskId)).toBe(true)
        expect(state.hasActiveTasks()).toBe(true)
      }),
      { numRuns: 100 }
    )
    
    fc.assert(
      fc.property(repositoryIdArb, inactiveStatusArb, (repositoryId, status) => {
        // Reset store at start of each iteration
        useAnalysisProgressStore.setState({ tasks: {}, minimized: false })
        
        const taskId = getAIScanTaskId(repositoryId)
        
        useAnalysisProgressStore.getState().addTask({
          id: taskId,
          type: 'ai_scan',
          repositoryId,
          status,
          progress: 100,
          stage: 'completed',
          message: null,
        })
        
        const activeTasks = useAnalysisProgressStore.getState().getActiveTasks()
        
        // AI scan task with inactive status MUST NOT be in active tasks
        expect(activeTasks.some(t => t.id === taskId)).toBe(false)
      }),
      { numRuns: 100 }
    )
  })
})
