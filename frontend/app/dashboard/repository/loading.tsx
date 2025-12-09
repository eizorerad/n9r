export default function RepositoryLoading() {
    return (
        <div className="flex h-screen w-screen bg-[#1e1e1e] overflow-hidden text-foreground">
            {/* Activity Bar Placeholder */}
            <div className="w-[48px] h-full bg-[#1e1e1e] border-r border-[#2b2b2b] flex-shrink-0" />

            {/* Sidebar Skeleton */}
            <div className="hidden md:flex w-[300px] h-full bg-[#252526] border-r border-[#2b2b2b] flex-col flex-shrink-0">
                <div className="h-[35px] border-b border-[#2b2b2b] flex items-center px-4 bg-[#252526]">
                    <div className="h-3 w-20 bg-[#3c3c3c] rounded animate-pulse" />
                </div>
                <div className="p-3 space-y-4 mt-1 overflow-hidden">
                    {[1, 2, 3, 4, 5, 6].map((i) => (
                        <div key={i} className="flex flex-col gap-2">
                            <div className="flex items-center gap-2">
                                <div className="h-2 w-2 rounded-full bg-[#3c3c3c]" />
                                <div className="h-3 w-3/4 bg-[#3c3c3c] rounded animate-pulse" />
                            </div>
                            <div className="ml-4 h-2 w-1/2 bg-[#3c3c3c] rounded animate-pulse opacity-60" />
                        </div>
                    ))}
                </div>
            </div>

            {/* Main Content Skeleton */}
            <div className="flex-1 flex flex-col bg-[#1e1e1e] min-w-0">
                {/* Tabs Area */}
                <div className="h-9 bg-[#1e1e1e] border-b border-[#2b2b2b] flex items-center px-0">
                    <div className="h-full w-32 bg-[#252526] border-r border-[#2b2b2b] flex items-center px-3 gap-2">
                        <div className="h-3 w-3 rounded-full bg-[#3c3c3c]" />
                        <div className="h-3 w-16 bg-[#3c3c3c] rounded animate-pulse" />
                    </div>
                </div>

                {/* Editor Code Area */}
                <div className="flex-1 p-8 space-y-4 overflow-hidden">
                    {[30, 55, 45, 70, 35, 60, 40, 65, 50, 38, 58, 42].map((width, i) => (
                        <div
                            key={i}
                            className="h-4 bg-[#2b2b2b] rounded animate-pulse"
                            style={{ width: `${width}%`, opacity: 1 - (i * 0.05) }}
                        />
                    ))}
                </div>

                {/* Status Bar Skeleton */}
                <div className="h-[22px] border-t border-[#2b2b2b] bg-[#1e1e1e] flex items-center justify-between px-3">
                    <div className="flex items-center gap-3">
                        <div className="h-3 w-20 bg-[#333333] rounded animate-pulse" />
                        <div className="h-3 w-12 bg-[#333333] rounded animate-pulse" />
                    </div>
                    <div className="h-3 w-16 bg-[#333333] rounded animate-pulse" />
                </div>
            </div>
        </div>
    )
}
