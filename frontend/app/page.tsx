import Link from "next/link";
import { Github, Zap, Shield, LineChart, Code2, ArrowRight } from "lucide-react";

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-b from-gray-950 to-gray-900 text-white">
      {/* Header */}
      <header className="border-b border-gray-800">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center font-bold">
              n9
            </div>
            <span className="text-xl font-semibold">n9r</span>
          </div>
          <nav className="hidden md:flex items-center gap-8">
            <Link href="#features" className="text-gray-400 hover:text-white transition">
              Features
            </Link>
            <Link href="/playground" className="text-gray-400 hover:text-white transition">
              Playground
            </Link>
            <Link href="#pricing" className="text-gray-400 hover:text-white transition">
              Pricing
            </Link>
          </nav>
          <Link
            href="/auth/login"
            className="flex items-center gap-2 bg-white text-gray-900 px-4 py-2 rounded-lg font-medium hover:bg-gray-100 transition"
          >
            <Github className="w-5 h-5" />
            Sign in with GitHub
          </Link>
        </div>
      </header>

      {/* Hero Section */}
      <section className="container mx-auto px-4 py-24 text-center">
        <div className="inline-flex items-center gap-2 bg-green-500/10 border border-green-500/20 text-green-400 px-4 py-2 rounded-full text-sm mb-8">
          <Zap className="w-4 h-4" />
          AI-Powered Code Quality Platform
        </div>
        <h1 className="text-5xl md:text-7xl font-bold mb-6 bg-gradient-to-r from-white to-gray-400 bg-clip-text text-transparent">
          AI Code Detox &<br />Auto-Healing Platform
        </h1>
        <p className="text-xl text-gray-400 max-w-2xl mx-auto mb-12">
          Automatically clean up AI-generated and legacy code, keeping your software
          projects architecturally healthy and maintainable.
        </p>
        <div className="flex flex-col sm:flex-row gap-4 justify-center">
          <Link
            href="/auth/login"
            className="flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white px-8 py-4 rounded-lg font-semibold text-lg transition"
          >
            Get Started Free
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            href="/playground"
            className="flex items-center justify-center gap-2 border border-gray-700 hover:border-gray-600 px-8 py-4 rounded-lg font-semibold text-lg transition"
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
        <p className="text-gray-400 text-center max-w-2xl mx-auto mb-16">
          n9r provides comprehensive tools to analyze, monitor, and automatically fix
          code quality issues across your repositories.
        </p>
        <div className="grid md:grid-cols-3 gap-8">
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-8">
            <div className="w-12 h-12 bg-blue-500/10 rounded-lg flex items-center justify-center mb-6">
              <LineChart className="w-6 h-6 text-blue-400" />
            </div>
            <h3 className="text-xl font-semibold mb-3">VCI Score Tracking</h3>
            <p className="text-gray-400">
              Monitor your codebase health with our Viability & Code-quality Index
              score. Track improvements over time with detailed metrics.
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-8">
            <div className="w-12 h-12 bg-green-500/10 rounded-lg flex items-center justify-center mb-6">
              <Shield className="w-6 h-6 text-green-400" />
            </div>
            <h3 className="text-xl font-semibold mb-3">Auto-Healing PRs</h3>
            <p className="text-gray-400">
              Let AI automatically fix detected issues and create pull requests.
              Review and merge with confidence using our AI-generated explanations.
            </p>
          </div>
          <div className="bg-gray-900/50 border border-gray-800 rounded-xl p-8">
            <div className="w-12 h-12 bg-purple-500/10 rounded-lg flex items-center justify-center mb-6">
              <Code2 className="w-6 h-6 text-purple-400" />
            </div>
            <h3 className="text-xl font-semibold mb-3">AI Code Chat</h3>
            <p className="text-gray-400">
              Ask questions about your code, get explanations for detected issues,
              and receive personalized refactoring suggestions.
            </p>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="container mx-auto px-4 py-24">
        <div className="bg-gradient-to-r from-green-500/20 to-emerald-500/20 border border-green-500/30 rounded-2xl p-12 text-center">
          <h2 className="text-3xl md:text-4xl font-bold mb-4">
            Ready to Clean Up Your Code?
          </h2>
          <p className="text-gray-300 max-w-xl mx-auto mb-8">
            Start free with up to 3 repositories. No credit card required.
          </p>
          <Link
            href="/auth/login"
            className="inline-flex items-center gap-2 bg-white text-gray-900 px-8 py-4 rounded-lg font-semibold text-lg hover:bg-gray-100 transition"
          >
            <Github className="w-5 h-5" />
            Continue with GitHub
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-800 py-12">
        <div className="container mx-auto px-4 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-gradient-to-br from-green-400 to-emerald-600 rounded flex items-center justify-center text-xs font-bold">
              n9
            </div>
            <span className="text-gray-400">© 2025 n9r. All rights reserved.</span>
          </div>
          <div className="flex items-center gap-6 text-sm text-gray-400">
            <Link href="/privacy" className="hover:text-white transition">
              Privacy
            </Link>
            <Link href="/terms" className="hover:text-white transition">
              Terms
            </Link>
            <Link href="https://github.com/n9r" className="hover:text-white transition">
              GitHub
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}
