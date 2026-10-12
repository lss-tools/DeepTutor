import { Suspense } from 'react'
import { ExamAttemptPage } from '@/components/learning/practice/ExamAttemptPage'
import { LearningSkeleton } from '@/components/learning/LearningShell'
import { QuizFollowupProvider } from '@/context/QuizFollowupContext'

export default function Page() {
  return <QuizFollowupProvider><Suspense fallback={<LearningSkeleton />}><ExamAttemptPage /></Suspense></QuizFollowupProvider>
}
