import { Suspense } from 'react'
import Link from 'next/link'
import { Github, AlertCircle } from 'lucide-react'
import { loginWithGitHub } from '@/app/actions/auth'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

function LoginForm({ error }: { error?: string }) {
  return (
    <Card className="w-full max-w-md bg-gray-900/50 border-gray-800">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 bg-gradient-to-br from-green-400 to-emerald-600 rounded-2xl flex items-center justify-center font-bold text-2xl">
            n9
          </div>
        </div>
        <CardTitle className="text-2xl">Welcome to n9r</CardTitle>
        <CardDescription>
          AI-powered code health monitoring and auto-healing
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
            <AlertCircle className="h-4 w-4 flex-shrink-0" />
            <span>{decodeURIComponent(error)}</span>
          </div>
        )}
        
        <form action={loginWithGitHub}>
          <Button 
            type="submit"
            className="w-full flex items-center justify-center gap-2 bg-gray-800 hover:bg-gray-700 text-white h-12"
          >
            <Github className="h-5 w-5" />
            Continue with GitHub
          </Button>
        </form>
        
        <p className="text-xs text-center text-gray-500 mt-4">
          By continuing, you agree to our{' '}
          <Link href="/terms" className="text-gray-400 hover:text-white underline">
            Terms of Service
          </Link>{' '}
          and{' '}
          <Link href="/privacy" className="text-gray-400 hover:text-white underline">
            Privacy Policy
          </Link>
        </p>
      </CardContent>
    </Card>
  )
}

function LoginContent({ searchParams }: { searchParams: { error?: string; redirect?: string } }) {
  return <LoginForm error={searchParams.error} />
}

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; redirect?: string }>
}) {
  const params = await searchParams
  
  return (
    <div className="min-h-screen bg-gray-950 text-white flex flex-col">
      {/* Header */}
      <header className="border-b border-gray-800/50">
        <div className="container mx-auto px-4 py-4">
          <Link href="/" className="flex items-center gap-2 w-fit">
            <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center font-bold text-sm">
              n9
            </div>
            <span className="text-xl font-semibold">n9r</span>
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-4">
        <Suspense fallback={<LoginFormSkeleton />}>
          <LoginContent searchParams={params} />
        </Suspense>
      </main>

      {/* Footer */}
      <footer className="border-t border-gray-800/50 py-6">
        <div className="container mx-auto px-4 text-center text-sm text-gray-500">
          <p>© 2025 n9r. All rights reserved.</p>
        </div>
      </footer>
    </div>
  )
}

function LoginFormSkeleton() {
  return (
    <Card className="w-full max-w-md bg-gray-900/50 border-gray-800 animate-pulse">
      <CardHeader className="text-center">
        <div className="flex justify-center mb-4">
          <div className="w-16 h-16 bg-gray-800 rounded-2xl" />
        </div>
        <div className="h-7 w-48 bg-gray-800 rounded mx-auto mb-2" />
        <div className="h-4 w-64 bg-gray-800 rounded mx-auto" />
      </CardHeader>
      <CardContent>
        <div className="h-12 w-full bg-gray-800 rounded" />
      </CardContent>
    </Card>
  )
}
