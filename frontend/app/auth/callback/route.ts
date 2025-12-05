import { NextRequest, NextResponse } from 'next/server'
import { handleGitHubCallback } from '@/app/actions/auth'

const APP_URL = process.env.NEXT_PUBLIC_APP_URL || 'http://localhost:3000'

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const code = searchParams.get('code')
  const error = searchParams.get('error')

  // Handle OAuth errors
  if (error) {
    const errorDescription = searchParams.get('error_description') || 'Authentication was cancelled'
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(errorDescription)}`, APP_URL)
    )
  }

  // Validate code
  if (!code) {
    return NextResponse.redirect(
      new URL('/login?error=No authorization code received', APP_URL)
    )
  }

  // Exchange code for session
  const result = await handleGitHubCallback(code)

  if (result.error) {
    return NextResponse.redirect(
      new URL(`/login?error=${encodeURIComponent(result.error)}`, APP_URL)
    )
  }

  // Redirect to dashboard on success
  return NextResponse.redirect(new URL('/dashboard', APP_URL))
}
