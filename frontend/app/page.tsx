import Link from "next/link";
import { Github, Zap, Shield, LineChart, Code2, ArrowRight } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="border-b border-border/50">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded-lg flex items-center justify-center font-bold shadow-sm">
              n9
            </div>
            <span className="text-xl font-semibold">n9r</span>
          </div>
          <nav className="hidden md:flex items-center gap-8">
            <Link href="#features" className="text-muted-foreground hover:text-foreground transition-colors">
              Features
            </Link>
            <Link href="/playground" className="text-muted-foreground hover:text-foreground transition-colors">
              Playground
            </Link>
            <Link href="#pricing" className="text-muted-foreground hover:text-foreground transition-colors">
              Pricing
            </Link>
          </nav>
          <Link
            href="/auth/login"
            className="flex items-center gap-2 bg-foreground text-background px-4 py-2 rounded-lg font-medium hover:bg-foreground/90 transition-colors"
          >
            <Github className="w-5 h-5" />
            Sign in with GitHub
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="inline-flex items-center gap-2 bg-primary/10 border border-primary/20 text-primary px-4 py-2 rounded-full text-sm mb-8">
          <Zap className="w-4 h-4" />
          AI-Powered Code Quality Platform
        </div>
        <h1 className="text-5xl md:text-7xl font-bold mb-6 bg-gradient-to-r from-foreground to-muted-foreground bg-clip-text text-transparent">
          AI Code Detox &<br />Auto-Healing Platform
        </h1>
        <p className="text-xl text-muted-foreground max-w-2xl mx-auto mb-12">
          Automatically clean up AI-generated and legacy code, keeping your software
          projects architecturally healthy and maintainable.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/auth/login"
            className="flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-primary-foreground px-8 py-4 rounded-lg font-semibold text-lg transition shadow-lg shadow-primary/20"
          >
            Get Started Free
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            href="/playground"
            className="flex items-center justify-center gap-2 border border-border hover:bg-muted/50 px-8 py-4 rounded-lg font-semibold text-lg transition-colors"
          >
            🧪 Try Playground
          </Link>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="container mx-auto px-4 py-24">
        <h2 className="text-3xl md:text-4xl font-bold text-center mb-4">
          Everything You Need for Clean Code
        </h2>
        <p className="text-muted-foreground text-center max-w-2xl mx-auto mb-16">
          n9r provides comprehensive tools to analyze, monitor, and automatically fix
          code quality issues across your repositories.
        </p>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="glass-panel border border-border/50 rounded-xl p-8">
            <div className="w-12 h-12 bg-blue-500/10 rounded-lg flex items-center justify-center mb-6">
              <LineChart className="w-6 h-6 text-blue-500" />
            </div>
            <h3 className="text-xl font-semibold mb-3">VCI Score Tracking</h3>
            <p className="text-muted-foreground">
              Monitor your codebase health with our Viability & Code-quality Index
              score. Track improvements over time with detailed metrics.
            </p>
          </div>
          <div className="glass-panel border border-border/50 rounded-xl p-8">
            <div className="w-12 h-12 bg-emerald-500/10 rounded-lg flex items-center justify-center mb-6">
              <Shield className="w-6 h-6 text-emerald-500" />
            </div>
            <h3 className="text-xl font-semibold mb-3">Auto-Healing PRs</h3>
            <p className="text-muted-foreground">
              Let AI automatically fix detected issues and create pull requests.
              Review and merge with confidence using our AI-generated explanations.
            </p>
          </div>
          <div className="glass-panel border border-border/50 rounded-xl p-8">
            <div className="w-12 h-12 bg-purple-500/10 rounded-lg flex items-center justify-center mb-6">
              <Code2 className="w-6 h-6 text-purple-500" />
            </div>
            <h3 className="text-xl font-semibold mb-3">AI Code Chat</h3>
            <p className="text-muted-foreground">
              Ask questions about your code, get explanations for detected issues,
              and receive personalized refactoring suggestions.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="container mx-auto px-4 py-24">
        <div className="bg-gradient-to-r from-primary/10 to-primary/5 border border-primary/20 rounded-2xl p-12 text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Ready to Clean Up Your Code?
          </h2>
          <p className="text-muted-foreground max-w-xl mx-auto mb-8">
            Start free with up to 3 repositories. No credit card required.
          </p>
          <Link
            href="/auth/login"
            className="inline-flex items-center gap-2 bg-foreground text-background px-8 py-4 rounded-lg font-semibold text-lg hover:bg-foreground/90 transition-colors"
          >
            <Github className="w-5 h-5" />
            Continue with GitHub
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-border/50 py-12">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-primary to-primary/80 text-primary-foreground rounded flex items-center justify-center text-xs font-bold shadow-sm">
              n9
            </div>
            <span className="text-muted-foreground">© 2025 n9r. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-muted-foreground">
            <Link href="/privacy" className="hover:text-foreground transition-colors">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-foreground transition-colors">
              Terms
            </Link>
            <Link href="https://github.com/n9r" className="hover:text-foreground transition-colors">
              GitHub
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
