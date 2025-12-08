"use client"

import { GitBranch, XCircle, AlertTriangle, Check, Bell } from "lucide-react"
import { cn } from "@/lib/utils"
import { useStatusBarStore } from "@/lib/stores/status-bar-store"

export function StatusBar({ className }: { className?: string }) {
    const { branch, fileType, cursorPosition, errors, warnings } = useStatusBarStore()

    return (
        <div className={cn("h-[22px] bg-[#1e1e1e] text-[#cccccc] border-t border-[#2b2b2b] flex items-center justify-between px-2 text-[11px] select-none font-sans", className)}>
            <div className="flex items-center gap-3">
                <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                    <GitBranch className="w-3 h-3" />
                    <span>{branch || 'main'}</span>
                </button>
                <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                    <XCircle className="w-3 h-3" />
                    <span>{errors}</span>
                    <AlertTriangle className="w-3 h-3 ml-1" />
                    <span>{warnings}</span>
                </button>
            </div>

            <div className="flex items-center gap-3">
                {cursorPosition && (
                    <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                        <div className="flex items-center gap-1">
                            <span>Ln {cursorPosition.ln}, Col {cursorPosition.col}</span>
                        </div>
                    </button>
                )}
                <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                    <span>UTF-8</span>
                </button>
                {fileType && (
                    <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                        <div className="flex items-center gap-1">
                            <span className="text-[10px]">{`{ }`}</span>
                            <span>{fileType}</span>
                        </div>
                    </button>
                )}
                <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                    <Check className="w-3 h-3" />
                    <span>Prettier</span>
                </button>
                <button className="flex items-center gap-1 hover:bg-white/10 px-1 rounded-sm h-[18px]">
                    <Bell className="w-3 h-3" />
                </button>
            </div>
        </div>
    )
}
