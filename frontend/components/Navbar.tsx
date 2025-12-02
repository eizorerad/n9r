"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Github } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function Navbar() {
    const pathname = usePathname();
    const isPlayground = pathname === "/playground";

    return (
        <nav className="fixed top-4 left-1/2 -translate-x-1/2 w-[95%] max-w-5xl z-50 rounded-2xl border border-white/10 bg-background/30 backdrop-blur-xl shadow-lg shadow-black/5 transition-all duration-300 hover:bg-background/40 hover:shadow-xl hover:border-white/20">
            <div className="px-4 py-3 flex items-center justify-between">
                <Link href="/" className="flex items-center gap-2 group">
                    <div className="w-8 h-8 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded-lg flex items-center justify-center font-bold text-sm shadow-sm group-hover:scale-105 transition-transform">
                        n9
                    </div>
                    <span className="text-xl font-semibold">n9r<span className="text-primary/60">.ai</span></span>
                </Link>

                <div className="flex items-center gap-4">
                    {!isPlayground && (
                        <Link href="/playground" className="text-sm font-medium text-muted-foreground hover:text-foreground transition-colors hidden md:block">
                            Playground
                        </Link>
                    )}

                    <Link href="/auth/login">
                        <Button
                            variant="ghost"
                            size="sm"
                            className="rounded-xl bg-white/5 hover:bg-white/10 border border-white/5 hover:border-white/10 transition-all text-foreground font-medium"
                        >
                            <Github className="w-4 h-4 mr-2" />
                            Sign In
                        </Button>
                    </Link>
                </div>
            </div>
        </nav>
    );
}
