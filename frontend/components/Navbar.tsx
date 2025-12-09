"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import { Github } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function Navbar() {
    const pathname = usePathname();
    const isPlayground = pathname === "/playground";

    return (
        <nav className="fixed top-4 left-1/2 -translate-x-1/2 w-[95%] max-w-5xl z-50 rounded-2xl border border-white/10 bg-background/30 backdrop-blur-xl shadow-lg shadow-black/5 transition-all duration-300 hover:bg-background/40 hover:shadow-xl hover:border-white/20">
            <div className="px-4 py-3 flex items-center justify-between">
                <Link href="/" className="flex items-center gap-2 group">
                    <Image 
                        src="/logo.svg" 
                        alt="Necromancer Logo" 
                        width={32} 
                        height={32} 
                        className="group-hover:scale-105 transition-transform"
                    />
                    <span className="text-xl font-semibold">Necromancer</span>
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
