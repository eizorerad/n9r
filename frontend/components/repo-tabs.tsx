"use client"

import { useState } from "react"
import { Brain, Network, Bug, X } from "lucide-react" // Importing icons as requested replacements for file extensions
import { cn } from "@/lib/utils"

interface RepoTabsProps {
    aiScanContent: React.ReactNode
    semanticAnalysisContent: React.ReactNode
    staticAnalysisContent: React.ReactNode
}

type TabType = "ai-scan" | "semantic" | "static"

export function RepoTabs({
    aiScanContent,
    semanticAnalysisContent,
    staticAnalysisContent,
}: RepoTabsProps) {
    const [activeTab, setActiveTab] = useState<TabType>("ai-scan")

    const tabs = [
        {
            id: "ai-scan" as TabType,
            label: "AI Scan",
            icon: <Brain className="w-3.5 h-3.5 text-primary" />,
            content: aiScanContent,
        },
        {
            id: "semantic" as TabType,
            label: "Semantic Analysis",
            icon: <Network className="w-3.5 h-3.5 text-primary" />,
            content: semanticAnalysisContent,
        },
        {
            id: "static" as TabType,
            label: "Static Analysis (Issues)",
            icon: <Bug className="w-3.5 h-3.5 text-primary" />,
            content: staticAnalysisContent,
        },
    ]

    return (
        <div className="flex flex-col h-full">
            {/* Scrollable Tab Bar */}
            <div className="h-[35px] bg-[#1e1e1e] flex items-center border-b border-[#252526] overflow-x-auto scroller-hidden">
                {tabs.map((tab) => {
                    const isActive = activeTab === tab.id
                    return (
                        <button
                            key={tab.id}
                            onClick={() => setActiveTab(tab.id)}
                            className={cn(
                                "h-full px-3 flex items-center gap-2 border-r border-[#252526] min-w-fit cursor-pointer text-[13px] transition-colors select-none",
                                isActive
                                    ? "bg-[#1e1e1e] text-[#ffffff] border-t-2 border-t-[#007fd4]"
                                    : "bg-[#2d2d2d] text-[#969696] hover:bg-[#2a2d2e] border-t-2 border-t-transparent"
                            )}
                        >
                            {tab.icon}
                            <span className={cn("truncate", !isActive && "italic")}>{tab.label}</span>
                            <span className="ml-2 hover:bg-[#333] rounded-sm p-0.5 opacity-0 group-hover:opacity-100">
                                <X className="w-3 h-3" />
                            </span>
                        </button>
                    )
                })}
            </div>

            {/* Breadcrumbs Area (Optional, mimics VSCode path under tabs) */}
            <div className="h-[22px] flex items-center px-4 text-[13px] text-[#888888] select-none bg-[#1e1e1e]">
                <span>repository</span>
                <span className="mx-1">›</span>
                <span>analysis</span>
                <span className="mx-1">›</span>
                <span className="text-foreground">{tabs.find(t => t.id === activeTab)?.label}</span>
            </div>

            {/* Active Content Area */}
            <div className="flex-1 overflow-hidden bg-[#1e1e1e] p-0">
                <div className="h-full w-full">
                    {tabs.find((tab) => tab.id === activeTab)?.content}
                </div>
            </div>
        </div>
    )
}
