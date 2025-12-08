"use client"

import { ActivityBar } from "./activity-bar"
import { Sidebar } from "./sidebar"
import { StatusBar } from "./status-bar"

interface WorkbenchProps {
    children: React.ReactNode
    sidebar?: React.ReactNode
    activeView?: string
    onViewChange?: (view: string) => void
}

export function Workbench({ children, sidebar, activeView, onViewChange }: WorkbenchProps) {
    return (
        <div className="flex flex-col h-screen w-screen bg-background text-foreground overflow-hidden">
            {/* Top Section */}
            <div className="flex flex-1 overflow-hidden">
                <ActivityBar activeView={activeView} onViewChange={onViewChange} />
                {sidebar === undefined ? <Sidebar /> : sidebar}

                {/* Main Editor Area */}
                <div className="flex-1 flex flex-col min-w-0 bg-[#1e1e1e]">
                    {/* Content */}
                    <div className="flex-1 overflow-auto relative flex flex-col">
                        {children}
                    </div>
                </div>
            </div>

            {/* Status Bar */}
            <StatusBar />
        </div>
    )
}
