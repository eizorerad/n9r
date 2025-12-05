import { redirect } from 'next/navigation'
import { getSession } from '@/lib/session'
import { IDEClient } from './ide-client'

export default async function IDEPage({
  params
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = await params
  const session = await getSession()

  if (!session?.accessToken) {
    redirect('/login')
  }

  return <IDEClient id={id} token={session.accessToken} />
}
