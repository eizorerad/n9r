'use client'

import { useEffect, useState } from 'react'
import { useActionState } from 'react'
import Link from 'next/link'
import { ArrowLeft, GitBranch, Lock, Globe, Loader2, RefreshCw } from 'lucide-react'
import { connectRepository, getAvailableRepositories } from '@/app/actions/repository'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'


interface Repository {
  id?: number
  github_id?: number
  name: string
  full_name: string
  private: boolean
  description: string | null
  language: string | null
  default_branch: string
}

const initialState = {
  error: null as string | null,
  success: false,
}

export default function ConnectRepositoryPage() {
  const [repos, setRepos] = useState<Repository[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [state, formAction, pending] = useActionState(
    async (_prevState: typeof initialState, formData: FormData) => {
      const result = await connectRepository(formData)
      if (result.error) {
        return { error: result.error, success: false }
      }
      return { error: null, success: true }
    },
    initialState
  )

  const loadRepositories = async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const result = await getAvailableRepositories()
      if (result.error) {
        setLoadError(result.error)
      } else {
        setRepos(result.repositories || [])
      }
    } catch {
      setLoadError('Failed to load repositories')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadRepositories()
  }, [])

  if (state.success) {
    return (
      <div className="min-h-screen bg-background text-foreground flex items-center justify-center">
        <Card className="glass-panel border-border/50 max-w-md w-full">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-emerald-500/10 rounded-full flex items-center justify-center mx-auto mb-4 border border-emerald-500/20">
              <GitBranch className="w-8 h-8 text-emerald-500" />
            </div>
            <CardTitle>Repository Connected!</CardTitle>
            <CardDescription>
              Your repository has been connected successfully.
            </CardDescription>
          </CardHeader>
          <CardContent className="flex justify-center">
            <Link href="/dashboard">
              <Button>Go to Dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#1e1e1e] border-b border-neutral-700/50">
        <div className="container mx-auto px-6 py-3">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="p-2 hover:bg-neutral-800 rounded-lg transition-colors text-neutral-400 hover:text-neutral-200">
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <div className="flex items-center gap-3">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/logo.svg"
                alt="n9r"
                className="w-8 h-8"
              />
              <span className="text-lg font-semibold tracking-tight text-neutral-200">n9r</span>
            </div>
            <span className="text-neutral-600 text-lg font-light">/</span>
            <span className="text-neutral-400 font-mono text-sm">Connect Repository</span>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-6 py-10 max-w-3xl">
        <Card className="glass-panel border-border/50">
          <CardHeader>
            <CardTitle>Connect a Repository</CardTitle>
            <CardDescription>
              Select a repository from your GitHub account to connect with n9r.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {state.error && (
              <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm font-medium">
                {state.error}
              </div>
            )}

            {loadError && (
              <div className="mb-6 p-4 bg-destructive/10 border border-destructive/20 rounded-lg text-destructive text-sm flex items-center justify-between">
                <span>{loadError}</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={loadRepositories}
                  className="text-destructive hover:text-destructive hover:bg-destructive/10"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Retry
                </Button>
              </div>
            )}

            {loading ? (
              <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
                <Loader2 className="h-10 w-10 animate-spin mb-4 text-primary" />
                <span>Loading repositories...</span>
              </div>
            ) : repos.length === 0 && !loadError ? (
              <div className="text-center py-16 text-muted-foreground">
                <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-20" />
                <p className="font-medium">No repositories found</p>
                <p className="text-sm mt-2 opacity-60">Make sure you have repositories on your GitHub account.</p>
              </div>
            ) : (
              <form action={formAction} className="space-y-8">
                {/* Repository Selection */}
                <div className="space-y-4">
                  <label className="text-sm font-medium text-foreground block">
                    Select Repository <span className="text-muted-foreground ml-1">({repos.length} available)</span>
                  </label>
                  <div className="space-y-2 max-h-[400px] overflow-y-auto pr-2 custom-scrollbar">
                    {repos.map((repo) => (
                      <label
                        key={repo.id || repo.github_id}
                        className="flex items-center gap-4 p-4 border border-border rounded-xl cursor-pointer hover:bg-muted/30 hover:border-border/80 transition-all has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:checked]:shadow-sm group"
                      >
                        <input
                          type="radio"
                          name="github_id"
                          value={repo.github_id || repo.id}
                          className="sr-only"
                        />
                        <div className="p-2 rounded-lg bg-muted group-has-[:checked]:bg-primary/10 group-has-[:checked]:text-primary transition-colors">
                          <GitBranch className="h-5 w-5 text-muted-foreground group-has-[:checked]:text-primary" />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate text-foreground">{repo.full_name}</div>
                          {repo.description && (
                            <div className="text-xs text-muted-foreground truncate mt-0.5">{repo.description}</div>
                          )}
                          <div className="flex items-center gap-2 mt-2">
                            {repo.language && (
                              <Badge variant="secondary" className="text-[10px] px-1.5 py-0 h-5 font-normal">
                                {repo.language}
                              </Badge>
                            )}
                            <span className="text-xs text-muted-foreground flex items-center gap-1">
                              <GitBranch className="h-3 w-3" />
                              {repo.default_branch}
                            </span>
                          </div>
                        </div>
                        {repo.private ? (
                          <Lock className="h-4 w-4 text-muted-foreground/50 flex-shrink-0" />
                        ) : (
                          <Globe className="h-4 w-4 text-muted-foreground/50 flex-shrink-0" />
                        )}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Hidden field for full_name */}
                <input type="hidden" name="full_name" id="full_name" />

                {/* Mode Selection */}
                <div className="space-y-4">
                  <label className="text-sm font-medium text-foreground block">
                    Analysis Mode
                  </label>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                    <label className="flex flex-col items-center p-4 border border-border rounded-xl cursor-pointer hover:bg-muted/30 hover:border-border/80 transition-all has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:checked]:shadow-sm text-center">
                      <input
                        type="radio"
                        name="mode"
                        value="view_only"
                        defaultChecked
                        className="sr-only"
                      />
                      <span className="text-sm font-medium mb-1">View Only</span>
                      <span className="text-xs text-muted-foreground">Read & analyze code without making changes</span>
                    </label>
                    <label className="flex flex-col items-center p-4 border border-border rounded-xl cursor-pointer hover:bg-muted/30 hover:border-border/80 transition-all has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:checked]:shadow-sm text-center">
                      <input
                        type="radio"
                        name="mode"
                        value="assisted"
                        className="sr-only"
                      />
                      <span className="text-sm font-medium mb-1">Assisted</span>
                      <span className="text-xs text-muted-foreground">Get suggestions and fix issues manually</span>
                    </label>
                    <label className="flex flex-col items-center p-4 border border-border rounded-xl cursor-pointer hover:bg-muted/30 hover:border-border/80 transition-all has-[:checked]:border-primary has-[:checked]:bg-primary/5 has-[:checked]:shadow-sm text-center">
                      <input
                        type="radio"
                        name="mode"
                        value="auto_fix"
                        className="sr-only"
                      />
                      <span className="text-sm font-medium mb-1">Auto-Fix</span>
                      <span className="text-xs text-muted-foreground">Automatically create PRs for fixes</span>
                    </label>
                  </div>
                </div>

                {/* Submit */}
                <div className="flex gap-4 pt-4">
                  <Link href="/dashboard" className="flex-1">
                    <Button variant="outline" className="w-full" type="button">
                      Cancel
                    </Button>
                  </Link>
                  <Button
                    type="submit"
                    disabled={pending || repos.length === 0}
                    className="flex-1 bg-neutral-700 hover:bg-neutral-600 text-neutral-200 font-mono border border-neutral-600 shadow-none"
                  >
                    {pending ? (
                      <>
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                        Connecting...
                      </>
                    ) : (
                      'Connect Repository'
                    )}
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </main>
    </div>
  )
}
