import { Suspense } from 'react'
import { ExamAttemptPage } from '@/components/learning/practice/ExamAttemptPage'
import { LearningSkeleton } from '@/components/learning/LearningShell'

export default function Page() {
  return <Suspense fallback={<LearningSkeleton />}><ExamAttemptPage /></Suspense>
}
