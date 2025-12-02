import type { Metadata } from "next";
import { Outfit, JetBrains_Mono } from "next/font/google";
import { QueryProvider } from "@/providers/query-provider";
import { AnalysisProgressOverlay } from "@/components/analysis-progress-overlay";
import "./globals.css";

const outfit = Outfit({
  variable: "--font-sans",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "n9r - AI Code Detox & Auto-Healing Platform",
  description:
    "Automatically clean up AI-generated and legacy code, keeping software projects architecturally healthy.",
  keywords: ["code quality", "AI", "refactoring", "tech debt", "auto-healing"],
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <body
        className={`${outfit.variable} ${jetbrainsMono.variable} font-sans antialiased`}
      >
        <QueryProvider>
          {children}
          <AnalysisProgressOverlay />
        </QueryProvider>
      </body>
    </html>
  );
}
