import { NextRequest, NextResponse } from 'next/server'
import { decryptEdge } from '@/lib/session-edge'

// Protected routes that require authentication
const protectedRoutes = ['/dashboard', '/repo']

// Public routes that authenticated users should skip
const publicRoutes = ['/login', '/signup']

export async function middleware(request: NextRequest) {
  const path = request.nextUrl.pathname
  const errorParam = request.nextUrl.searchParams.get('error')

  // Skip middleware for API routes, static files, and auth callback
  if (
    path.startsWith('/api') ||
    path.startsWith('/_next') ||
    path.startsWith('/auth/callback') ||
    path.includes('.')
  ) {
    return NextResponse.next()
  }

  // Check if route is protected
  const isProtectedRoute = protectedRoutes.some(route => path.startsWith(route))
  const isPublicRoute = publicRoutes.includes(path)

  // Get session from cookie
  const sessionCookie = request.cookies.get('n9r_session')?.value
  const session = await decryptEdge(sessionCookie)

  // Redirect unauthenticated users to login
  if (isProtectedRoute && !session?.userId) {
    const loginUrl = new URL('/login', request.url)
    loginUrl.searchParams.set('redirect', path)
    return NextResponse.redirect(loginUrl)
  }

  // If we were redirected to login due to an expired token, clear the stale session cookie here.
  // Cookie mutations are allowed in middleware responses (unlike Server Component render).
  if (path === '/login' && errorParam === 'session_expired') {
    const response = NextResponse.next()
    response.cookies.delete('n9r_session')
    return response
  }

  // Redirect authenticated users away from public routes
  if (isPublicRoute && session?.userId) {
    return NextResponse.redirect(new URL('/dashboard', request.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public folder)
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
