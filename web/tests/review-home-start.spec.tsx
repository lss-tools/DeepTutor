import { act, fireEvent, render, screen } from '@testing-library/react'
import { expect, it, vi } from 'vitest'
import { ReviewHome } from '@/components/learning/practice/ReviewHome'
import { initI18n } from '@/i18n/init'
import * as api from '@/lib/practice-api'

vi.mock('@/hooks/useChatWorkspaces', () => ({
  useChatWorkspaces: () => ({ workspaces: [], error: '' }),
}))
vi.mock('@/components/learning/LibraryWorkspace', () => ({
  useLearningCreation: () => ({ begin: vi.fn(), dialog: null }),
}))
vi.mock('@/components/learning/LearningShell', () => ({
  LearningShell: ({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) => (
    <main>{action}{children}</main>
  ),
  LearningErrorState: () => null,
}))
vi.mock('@/components/learning/practice/PracticeSession', () => ({
  PracticeSession: ({ questions }: { questions: { id: number }[] }) => (
    <div data-testid="practice-session">{questions.length} questions</div>
  ),
}))
vi.mock('@/components/learning/practice/PracticeImport', () => ({ PracticeImport: () => null }))
vi.mock('@/components/learning/practice/PracticeInsights', () => ({ PracticeInsights: () => null }))
vi.mock('@/lib/practice-api', async original => ({
  ...(await original<typeof api>()),
  getPracticeSummary: vi.fn(),
  getPracticeQueue: vi.fn(),
}))

initI18n('en')

it("keeps the start button's icon mounted while today's review queue loads", async () => {
  let finish!: (value: Awaited<ReturnType<typeof api.getPracticeQueue>>) => void
  vi.mocked(api.getPracticeSummary).mockResolvedValue({
    total: 1,
    mistakes: 1,
    due: 1,
    overdue: 1,
    reviewed_today: 0,
    next_due_at: null,
    day_end: 100,
    timezone: 'UTC',
  })
  vi.mocked(api.getPracticeQueue).mockImplementation(
    () => new Promise(resolve => { finish = resolve }),
  )
  render(<ReviewHome />)

  const button = await screen.findByRole('button', { name: "Start today's review" })
  const icon = button.querySelector('svg')
  expect(icon).not.toBeNull()
  fireEvent.click(button)
  expect(button).toBeDisabled()
  expect(button.querySelector('svg')).toBe(icon)
  expect(icon).toHaveClass('animate-pulse')

  await act(async () => finish([
    {
      entry: { id: 1 },
      state: { version: 1, review_count: 0, is_mistake: true, due_at: 100 },
    } as unknown as Awaited<ReturnType<typeof api.getPracticeQueue>>[number],
  ]))
  expect(await screen.findByTestId('practice-session')).toHaveTextContent('1 questions')
})
