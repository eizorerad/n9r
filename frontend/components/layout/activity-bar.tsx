"use client"

import { Files, Search, GitBranch, Bug, Blocks, User, Settings } from "lucide-react"
import { cn } from "@/lib/utils"
import { useState } from "react"
import Link from "next/link"
import Image from "next/image"

interface ActivityBarProps {
    className?: string
    activeView?: string
    onViewChange?: (view: string) => void
}

export function ActivityBar({ className, activeView, onViewChange }: ActivityBarProps) {
    // If no controlled props provided, fallback to local state (though likely won't be used in this new flow)
    const [localActive, setLocalActive] = useState("explorer")
    const active = activeView || localActive
    const handleViewChange = (id: string) => {
        if (onViewChange) {
            onViewChange(id)
        } else {
            setLocalActive(id)
        }
    }

    const topItems = [
        { id: "explorer", icon: Files, label: "Explorer" },
        { id: "search", icon: Search, label: "Search" },
        { id: "source-control", icon: GitBranch, label: "Source Control" },
        { id: "run-debug", icon: Bug, label: "Run and Debug" },
        { id: "extensions", icon: Blocks, label: "Extensions" },
    ]

    const bottomItems = [
        { id: "account", icon: User, label: "Accounts" },
        { id: "manage", icon: Settings, label: "Manage" },
    ]

    return (
        <div className={cn("w-[48px] flex flex-col items-center bg-secondary py-2 border-r border-[#252526] z-50", className)}>
            {/* Logo linking to dashboard - styled like other activity bar icons */}
            <Link
                href="/dashboard"
                className="h-12 w-full flex items-center justify-center relative group opacity-60 hover:opacity-100 transition-none"
                title="Go to Dashboard"
            >
                <Image
                    src="/logo.svg"
                    alt="Logo"
                    width={24}
                    height={24}
                    className="grayscale brightness-75 group-hover:grayscale-0 group-hover:brightness-100 transition-all"
                />
            </Link>

            <div className="flex flex-col gap-0 w-full">
                {topItems.map((item) => (
                    <button
                        key={item.id}
                        onClick={() => handleViewChange(item.id)}
                        className={cn(
                            "h-12 w-full flex items-center justify-center relative group opacity-100 transition-none",
                            active === item.id ? "opacity-100" : "opacity-60 hover:opacity-100"
                        )}
                        title={item.label}
                    >
                        {active === item.id && (
                            <div className="absolute left-0 top-0 bottom-0 w-[2px] bg-white" />
                        )}
                        <item.icon
                            className={cn(
                                "w-6 h-6 stroke-[1.5]",
                                active === item.id ? "text-white" : "text-[#858585] group-hover:text-white"
                            )}
                        />
                    </button>
                ))}
            </div>

            <div className="mt-auto flex flex-col gap-0 w-full">
                {bottomItems.map((item) => (
                    <button
                        key={item.id}
                        className="h-12 w-full flex items-center justify-center relative group opacity-60 hover:opacity-100 transition-none"
                        title={item.label}
                    >
                        <item.icon className="w-6 h-6 stroke-[1.5] text-[#858585] group-hover:text-white" />
                    </button>
                ))}
            </div>
        </div>
    )
}
