import { getValidatedSession } from '@/lib/session'

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode
}) {
  // Validate session with backend before rendering any dashboard content
  // This will redirect to /login if the token is invalid or expired
  await getValidatedSession()

  return <>{children}</>
}
