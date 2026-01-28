/**
 * Unit Tests for IssuesList
 * 
 * Validates rendering, interaction, and expansion logic for Static Analysis issues.
 */

import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { IssuesList } from '@/components/issues-list'

// Mock icons to avoid rendering issues
vi.mock('lucide-react', async () => {
    const actual = await vi.importActual('lucide-react')
    return {
        ...actual,
        // Add any necessary mocks if needed, but actual should work for tests usually
    }
})

const mockIssues = [
    {
        id: 'issue-1',
        type: 'maintainability',
        severity: 'high' as const,
        title: 'High Severity Issue',
        description: 'This is a high severity issue description.',
        file_path: 'src/main.ts',
        line_start: 10,
        confidence: 0.9,
        status: 'open',
        auto_fixable: true,
        found_by_models: ['gpt-4', 'claude-3'],
    },
    {
        id: 'issue-2',
        type: 'bug',
        severity: 'medium' as const,
        title: 'Medium Severity Issue',
        description: 'This is a medium severity issue description.',
        file_path: 'src/utils.ts',
        line_start: 42,
        confidence: 0.8,
        status: 'open',
        auto_fixable: false,
        found_by_models: ['claude-3'],
    },
]

describe('IssuesList', () => {
    it('should render correct number of issues', () => {
        render(<IssuesList issues={mockIssues} />)
        expect(screen.getByText('Issues (2)')).toBeInTheDocument()
        expect(screen.getByText('High Severity Issue')).toBeInTheDocument()
        expect(screen.getByText('Medium Severity Issue')).toBeInTheDocument()
    })

    it('should be collapsed by default', () => {
        render(<IssuesList issues={mockIssues} />)
        // Titles visible
        expect(screen.getByText('High Severity Issue')).toBeInTheDocument()
        // Descriptions hidden (queryByText returns null if not found)
        expect(screen.queryByText('This is a high severity issue description.')).not.toBeInTheDocument()
    })

    it('should expand individual issue on click', async () => {
        const user = userEvent.setup()
        render(<IssuesList issues={mockIssues} />)

        // Click the first issue
        await user.click(screen.getByText('High Severity Issue'))

        // Verify description is visible
        await waitFor(() => {
            expect(screen.getByText('This is a high severity issue description.')).toBeVisible()
        })

        // Other description still hidden
        expect(screen.queryByText('This is a medium severity issue description.')).not.toBeInTheDocument()

        // Click again to collapse
        await user.click(screen.getByText('High Severity Issue'))
        await waitFor(() => {
            expect(screen.queryByText('This is a high severity issue description.')).not.toBeInTheDocument()
        })
    })

    it('should toggle all issues with the expand/collapse all button', async () => {
        const user = userEvent.setup()
        render(<IssuesList issues={mockIssues} />)

        // Initially collapsed
        expect(screen.queryByText('This is a high severity issue description.')).not.toBeInTheDocument()

        // Find Expand All button (title="Expand all")
        const expandAllBtn = screen.getByTitle('Expand all')
        await user.click(expandAllBtn)

        // Verify all expanded
        await waitFor(() => {
            expect(screen.getByText('This is a high severity issue description.')).toBeVisible()
            expect(screen.getByText('This is a medium severity issue description.')).toBeVisible()
        })

        // Button should change to Collapse all
        const collapseAllBtn = screen.getByTitle('Collapse all')
        expect(collapseAllBtn).toBeInTheDocument()

        // Click Collapse All
        await user.click(collapseAllBtn)

        // Verify all collapsed
        await waitFor(() => {
            expect(screen.queryByText('This is a high severity issue description.')).not.toBeInTheDocument()
            expect(screen.queryByText('This is a medium severity issue description.')).not.toBeInTheDocument()
        })
    })

    it('should show empty state when no issues provided', () => {
        render(<IssuesList issues={[]} />)
        expect(screen.getByText('No issues found')).toBeInTheDocument()
    })
})
