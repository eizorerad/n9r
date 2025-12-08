import { create } from 'zustand'

interface StatusBarState {
    branch: string | null
    fileType: string | null // e.g., 'TypeScript React', 'Python'
    cursorPosition: { ln: number; col: number } | null
    errors: number
    warnings: number

    // Actions
    setBranch: (branch: string | null) => void
    setFileInfo: (type: string | null) => void
    setCursorPosition: (ln: number, col: number) => void
    setDiagnostics: (errors: number, warnings: number) => void
    reset: () => void
}

export const useStatusBarStore = create<StatusBarState>((set) => ({
    branch: null,
    fileType: null,
    cursorPosition: null,
    errors: 0,
    warnings: 0,

    setBranch: (branch) => set({ branch }),
    setFileInfo: (fileType) => set({ fileType }),
    setCursorPosition: (ln, col) => set({ cursorPosition: { ln, col } }),
    setDiagnostics: (errors, warnings) => set({ errors, warnings }),
    reset: () => set({
        branch: null,
        fileType: null,
        cursorPosition: null,
        errors: 0,
        warnings: 0
    })
}))
