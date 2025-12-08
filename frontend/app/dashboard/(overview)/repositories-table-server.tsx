'use client'

import { useRouter } from 'next/navigation'
import { RepositoriesTable } from '@/components/repositories-table'
import type { Repository } from '@/lib/data/repositories'

interface RepositoriesTableServerProps {
  initialData: Repository[]
}

export function RepositoriesTableServer({ initialData }: RepositoriesTableServerProps) {
  const router = useRouter()

  const handleRowClick = (repo: Repository) => {
    router.push(`/dashboard/repository/${repo.id}`)
  }

  return (
    <RepositoriesTable
      data={initialData}
      onRowClick={handleRowClick}
    />
  )
}
