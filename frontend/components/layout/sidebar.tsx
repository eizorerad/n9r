"use client"

import { MoreHorizontal } from "lucide-react"
import { cn } from "@/lib/utils"

interface SidebarProps {
    className?: string
    children?: React.ReactNode
    title?: string
}

export function Sidebar({ className, children, title = "EXPLORER" }: SidebarProps) {
    return (
        <div className={cn("w-[300px] bg-[#252526] border-r border-[#1e1e1e] flex flex-col font-sans", className)}>
            <div className="h-[35px] flex items-center justify-between px-4 text-[11px] font-bold text-[#bbbbbb] select-none tracking-wider uppercase">
                <span>{title}</span>
                <button className="hover:bg-white/10 rounded p-1">
                    <MoreHorizontal className="w-4 h-4" />
                </button>
            </div>

            <div className="flex-1 overflow-auto custom-scrollbar">
                {children}
            </div>
        </div>
    )
}
