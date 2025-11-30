'use client'

import { useEffect, useState } from 'react'
import { useActionState } from 'react'
import Link from 'next/link'
import { ArrowLeft, GitBranch, Lock, Globe, Loader2, RefreshCw } from 'lucide-react'
import { connectRepository, getAvailableRepositories } from '@/app/actions/repository'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'

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
      <div className="min-h-screen bg-gray-950 text-white flex items-center justify-center">
        <Card className="bg-gray-900/50 border-gray-800 max-w-md w-full">
          <CardHeader className="text-center">
            <div className="w-16 h-16 bg-green-500/10 rounded-full flex items-center justify-center mx-auto mb-4">
              <GitBranch className="w-8 h-8 text-green-500" />
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
    <div className="min-h-screen bg-gray-950 text-white">
      {/* Header */}
      <header className="border-b border-gray-800 bg-gray-900/50">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center gap-4">
            <Link href="/dashboard" className="p-2 hover:bg-gray-800 rounded-lg transition">
              <ArrowLeft className="h-5 w-5" />
            </Link>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 bg-gradient-to-br from-green-400 to-emerald-600 rounded-lg flex items-center justify-center font-bold text-sm">
                n9
              </div>
              <span className="text-xl font-semibold">n9r</span>
            </div>
            <span className="text-gray-400">/</span>
            <span className="text-gray-300">Connect Repository</span>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="container mx-auto px-4 py-8 max-w-2xl">
        <Card className="bg-gray-900/50 border-gray-800">
          <CardHeader>
            <CardTitle>Connect a Repository</CardTitle>
            <CardDescription>
              Select a repository from your GitHub account to connect with n9r.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {state.error && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm">
                {state.error}
              </div>
            )}

            {loadError && (
              <div className="mb-4 p-3 bg-red-500/10 border border-red-500/20 rounded-lg text-red-400 text-sm flex items-center justify-between">
                <span>{loadError}</span>
                <Button 
                  variant="ghost" 
                  size="sm" 
                  onClick={loadRepositories}
                  className="text-red-400 hover:text-red-300"
                >
                  <RefreshCw className="h-4 w-4 mr-1" />
                  Retry
                </Button>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="h-8 w-8 animate-spin text-gray-400" />
                <span className="ml-3 text-gray-400">Loading repositories...</span>
              </div>
            ) : repos.length === 0 && !loadError ? (
              <div className="text-center py-12 text-gray-400">
                <GitBranch className="h-12 w-12 mx-auto mb-4 opacity-50" />
                <p>No repositories found.</p>
                <p className="text-sm mt-2">Make sure you have repositories on your GitHub account.</p>
              </div>
            ) : (
              <form action={formAction} className="space-y-6">
                {/* Repository Selection */}
                <div className="space-y-3">
                  <label className="text-sm font-medium text-gray-300">
                    Select Repository ({repos.length} available)
                  </label>
                  <div className="space-y-2 max-h-96 overflow-y-auto">
                    {repos.map((repo) => (
                      <label
                        key={repo.id || repo.github_id}
                        className="flex items-center gap-3 p-3 border border-gray-800 rounded-lg cursor-pointer hover:border-gray-700 transition has-[:checked]:border-green-500 has-[:checked]:bg-green-500/5"
                      >
                        <input
                          type="radio"
                          name="github_id"
                          value={repo.github_id || repo.id}
                          className="sr-only"
                        />
                        <GitBranch className="h-5 w-5 text-gray-400 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="font-medium truncate">{repo.full_name}</div>
                          {repo.description && (
                            <div className="text-xs text-gray-500 truncate">{repo.description}</div>
                          )}
                          <div className="flex items-center gap-2 mt-1">
                            {repo.language && (
                              <span className="text-xs px-2 py-0.5 bg-gray-800 rounded text-gray-400">
                                {repo.language}
                              </span>
                            )}
                            <span className="text-xs text-gray-500">{repo.default_branch}</span>
                          </div>
                        </div>
                        {repo.private ? (
                          <Lock className="h-4 w-4 text-gray-500 flex-shrink-0" />
                        ) : (
                          <Globe className="h-4 w-4 text-gray-500 flex-shrink-0" />
                        )}
                      </label>
                    ))}
                  </div>
                </div>

                {/* Hidden field for full_name */}
                <input type="hidden" name="full_name" id="full_name" />

                {/* Mode Selection */}
                <div className="space-y-3">
                  <label className="text-sm font-medium text-gray-300">
                    Analysis Mode
                  </label>
                  <div className="grid grid-cols-3 gap-3">
                    <label className="flex flex-col items-center p-4 border border-gray-800 rounded-lg cursor-pointer hover:border-gray-700 transition has-[:checked]:border-green-500 has-[:checked]:bg-green-500/5">
                      <input
                        type="radio"
                        name="mode"
                        value="view_only"
                        defaultChecked
                        className="sr-only"
                      />
                      <span className="text-sm font-medium">View Only</span>
                      <span className="text-xs text-gray-500 mt-1">Read & analyze</span>
                    </label>
                    <label className="flex flex-col items-center p-4 border border-gray-800 rounded-lg cursor-pointer hover:border-gray-700 transition has-[:checked]:border-green-500 has-[:checked]:bg-green-500/5">
                      <input
                        type="radio"
                        name="mode"
                        value="assisted"
                        className="sr-only"
                      />
                      <span className="text-sm font-medium">Assisted</span>
                      <span className="text-xs text-gray-500 mt-1">Suggest fixes</span>
                    </label>
                    <label className="flex flex-col items-center p-4 border border-gray-800 rounded-lg cursor-pointer hover:border-gray-700 transition has-[:checked]:border-green-500 has-[:checked]:bg-green-500/5">
                      <input
                        type="radio"
                        name="mode"
                        value="auto_fix"
                        className="sr-only"
                      />
                      <span className="text-sm font-medium">Auto-Fix</span>
                      <span className="text-xs text-gray-500 mt-1">Create PRs</span>
                    </label>
                  </div>
                </div>

                {/* Submit */}
                <div className="flex gap-3">
                  <Link href="/dashboard" className="flex-1">
                    <Button variant="outline" className="w-full" type="button">
                      Cancel
                    </Button>
                  </Link>
                  <Button
                    type="submit"
                    disabled={pending || repos.length === 0}
                    className="flex-1 bg-green-600 hover:bg-green-700"
                  >
                    {pending ? 'Connecting...' : 'Connect Repository'}
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
