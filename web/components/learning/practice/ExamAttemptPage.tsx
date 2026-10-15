'use client'

import Link from 'next/link'
import Markdown from '@/components/common/MarkdownRenderer'
import PracticeAttachments from '@/components/learning/practice/PracticeAttachments'
import { practiceAssetMarkdown } from '@/lib/practice-content'
import { LearningErrorState, LearningShell } from '@/components/learning/LearningShell'
import {
  answerExamPosition,
  completeExamAttempt,
  createExamAttempt,
  getExamAttempt,
  getPracticeScoreHistory,
  getExamReadiness,
  recordExamModelScore,
  type ExamItem,
  type ExamAttempt,
  type ExamReadiness,
} from '@/lib/practice-api'
import { useEffect, useMemo, useState } from 'react'
import { useQuizFollowupController, useFollowupThread } from '@/context/QuizFollowupContext'

const SUBJECTS = [
  ['math', 'Математика'],
  ['russian', 'Русский язык'],
  ['physics', 'Физика'],
  ['informatics', 'Информатика'],
] as const

export function ExamAttemptPage() {
  const [subject, setSubject] = useState<string>('math')
  const [readiness, setReadiness] = useState<ExamReadiness | null>(null)
  const [attempt, setAttempt] = useState<ExamAttempt | null>(null)
  const [answer, setAnswer] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [refresh, setRefresh] = useState(0)
  const activeItem = useMemo(
    () => attempt?.items.find(item => !item.answered) ?? attempt?.items.at(-1) ?? null,
    [attempt]
  )

  useEffect(() => {
    let active = true
    setReadiness(null)
    void getExamReadiness(subject)
      .then(value => { if (active) setReadiness(value) })
      .catch(reason => { if (active) setError(String(reason)) })
    return () => { active = false }
  }, [subject, refresh])

  useEffect(() => {
    if (attempt || typeof window === 'undefined') return
    const savedId = window.localStorage.getItem(`oge-exam-attempt:${subject}`)
    if (!savedId) return
    let active = true
    setResuming(true)
    void getExamAttempt(savedId)
      .then(value => { if (active && value.exam_subject === subject) setAttempt(value) })
      .catch(() => window.localStorage.removeItem(`oge-exam-attempt:${subject}`))
      .finally(() => { if (active) setResuming(false) })
    return () => { active = false }
  }, [attempt, subject])

  useEffect(() => {
    setAnswer(activeItem?.answer ?? '')
  }, [activeItem?.position, activeItem?.answer])

  async function start() {
    setBusy(true)
    setError('')
    try {
      const value = await createExamAttempt(subject)
      setAttempt(value)
      window.localStorage.setItem(`oge-exam-attempt:${subject}`, value.attempt_id)
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function saveAnswer() {
    if (!attempt || !activeItem || busy) return
    setBusy(true)
    setError('')
    try {
      setAttempt(await answerExamPosition(attempt.attempt_id, activeItem.position, answer))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  async function finish() {
    if (!attempt || busy) return
    setBusy(true)
    setError('')
    try {
      setAttempt(await completeExamAttempt(attempt.attempt_id))
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    } finally {
      setBusy(false)
    }
  }

  function close() {
    if (attempt?.status === 'completed') {
      window.localStorage.removeItem(`oge-exam-attempt:${subject}`)
    }
    setAttempt(null)
    setError('')
    setRefresh(value => value + 1)
  }

  return (
    <LearningShell title="Вариант ОГЭ" subtitle="Попытка сохраняется по мере ответов.">
      <div className="mb-6 flex flex-wrap gap-2">
        {SUBJECTS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            disabled={Boolean(attempt)}
            onClick={() => { setSubject(value); setError('') }}
            aria-pressed={subject === value}
            className={`rounded-xl border px-3 py-2 text-sm ${subject === value ? 'border-primary bg-primary/10' : 'border-border'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {error && <LearningErrorState message={error} onRetry={() => setRefresh(value => value + 1)} />}

      {attempt?.is_partial && (
        <section role="status" className="mb-5 rounded-xl border border-border bg-card p-4 text-sm">
          <p className="font-medium">Неполный вариант ОГЭ</p>
          <p>Недостающие позиции: {attempt.missing_positions.join(', ')}.</p>
          <p>Баллы считаются только за включённые задания.</p>
        </section>
      )}

      {!attempt && !resuming && readiness && (
        <section className="rounded-2xl border border-border bg-card p-5">
          <h2 className="font-semibold">
            {readiness.ready ? 'Вариант готов' : `Не хватает позиций: ${readiness.missing_positions.length}`}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Для сборки нужны задания с подтверждённым эталоном и автоматической
            проверкой либо критериями для оценки решения.
          </p>
          {!readiness.ready && (
            <p className="mt-3 text-sm">Позиции: {readiness.missing_positions.join(', ')}</p>
          )}
          <button
            type="button"
            disabled={readiness.available_positions.length === 0 || busy}
            onClick={() => void start()}
            className="mt-5 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            {busy ? 'Создаю…' : readiness.ready ? 'Начать вариант' : 'Начать неполный вариант'}
          </button>
        </section>
      )}

      {attempt && attempt.status === 'in_progress' && attempt.items.some(item => !item.answered) && activeItem && (
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
          <div className="mb-5 flex items-center justify-between text-sm text-muted-foreground">
            <span>Позиция КИМ {activeItem.position} · заданий в попытке: {attempt.items.length}</span>
            <span>{attempt.items.filter(item => item.answered).length} ответов сохранено</span>
          </div>
          <progress
            className="mb-6 h-1.5 w-full accent-primary"
            max={attempt.items.length}
            value={attempt.items.filter(item => item.answered).length}
            aria-label="Ход выполнения варианта"
          />
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <Markdown content={practiceAssetMarkdown(activeItem.question.question, activeItem.question)} />
          </div>
          <PracticeAttachments entry={activeItem.question} inlineContent={activeItem.question.question} />
          {Object.keys(activeItem.question.options).length > 0 ? (
            <fieldset className="mt-6 space-y-3">
              <legend className="mb-3 text-sm font-medium">Выберите ответ</legend>
              {Object.entries(activeItem.question.options).map(([key, value]) => (
                <label key={key} className="flex cursor-pointer gap-3 rounded-xl border border-border p-3">
                  <input
                    type={['multi_choice', 'multiple_select'].includes(activeItem.question.question_type) ? 'checkbox' : 'radio'}
                    name={`position-${activeItem.position}`}
                    value={key}
                    checked={['multi_choice', 'multiple_select'].includes(activeItem.question.question_type)
                      ? answer.split(/[,;\s]+/).filter(Boolean).includes(key)
                      : answer === key}
                    onChange={event => {
                      if (!['multi_choice', 'multiple_select'].includes(activeItem.question.question_type)) {
                        setAnswer(key)
                        return
                      }
                      const selected = new Set(answer.split(/[,;\s]+/).filter(Boolean))
                      if (event.target.checked) selected.add(key)
                      else selected.delete(key)
                      setAnswer(Array.from(selected).sort().join(','))
                    }}
                  />
                  <span><b>{key}.</b> {value}</span>
                </label>
              ))}
            </fieldset>
          ) : (
            <label className="mt-6 block text-sm font-medium">
              Ответ
              {activeItem.question.checking_mode === 'model' ? (
                <textarea
                  value={answer}
                  onChange={event => setAnswer(event.target.value)}
                  rows={6}
                  className="mt-2 w-full rounded-xl border border-border bg-background p-3"
                />
              ) : (
                <input
                  value={answer}
                  onChange={event => setAnswer(event.target.value)}
                  className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-3"
                />
              )}
            </label>
          )}
          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" onClick={() => void saveAnswer()} disabled={busy} className="rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50">
              Сохранить ответ
            </button>
            <button type="button" onClick={close} disabled={busy} className="rounded-xl px-4 py-2.5 text-sm text-muted-foreground">
              Выйти и продолжить позже
            </button>
          </div>
        </section>
      )}

      {attempt && attempt.status === 'in_progress' && attempt.items.every(item => item.answered) && (
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
          <h2 className="text-lg font-semibold">Проверка ответов</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Автоматические ответы уже оценены. Развёрнутые решения проверьте с тьютором по критериям.
          </p>
          <div className="mt-5 space-y-4">
            {attempt.items.filter(item => item.earned_score === null).map(item => (
              <ModelGradePanel
                key={item.position}
                attemptId={attempt.attempt_id}
                item={item}
                onScored={setAttempt}
              />
            ))}
          </div>
          {attempt.items.every(item => item.earned_score !== null) && (
            <button type="button" onClick={() => void finish()} disabled={busy} className="mt-6 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50">
              Завершить вариант
            </button>
          )}
          <button type="button" onClick={close} disabled={busy} className="mt-4 block rounded-xl px-1 py-2 text-sm text-muted-foreground">
            Выйти и продолжить позже
          </button>
        </section>
      )}

      {attempt?.status === 'completed' && (
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
          <h2 className="text-xl font-semibold">Результат варианта</h2>
          <p className="mt-3 text-lg">Первичный балл: {attempt.total_score} / {attempt.maximum_score}</p>
          <p className="mt-1 text-sm text-muted-foreground">{attempt.scale_message}</p>
          <div className="mt-6 divide-y divide-border">
            {attempt.items.map(item => (
              <article key={item.position} className="py-4">
                <div className="flex justify-between gap-4 text-sm font-medium">
                  <span>Позиция {item.position}</span>
                  <span>{item.earned_score} / {item.max_score}</span>
                </div>
                <div className="prose prose-sm mt-2 max-w-none dark:prose-invert">
                  <Markdown content={item.question.explanation ?? ''} />
                </div>
              </article>
            ))}
          </div>
          <button type="button" onClick={close} className="mt-5 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground">
            К списку предметов
          </button>
        </section>
      )}

      <Link className="mt-6 inline-block text-sm underline" href="/learning/practice">К практике</Link>
    </LearningShell>
  )
}

function ModelGradePanel({
  attemptId,
  item,
  onScored,
}: {
  attemptId: string
  item: ExamItem
  onScored: (attempt: ExamAttempt) => void
}) {
  const key = `oge-exam:${attemptId}:${item.position}`
  const controller = useQuizFollowupController()
  const thread = useFollowupThread(key)
  const [grading, setGrading] = useState(false)
  const [baseline, setBaseline] = useState<string[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!grading || thread.isStreaming || thread.messages.at(-1)?.role !== 'assistant' || !baseline) return
    let active = true
    void getPracticeScoreHistory(item.entry_id)
      .then(async history => {
        if (!active) return
        const newGrade = history.items.find(score =>
          score.grading_source === 'model'
          && score.chat_session_id === thread.sessionId
          && !baseline.includes(score.attempt_id)
        )
        if (!newGrade) {
          setError('Тьютор не сохранил балл. Повторите проверку или отправьте решение на ручную оценку.')
          setGrading(false)
          return
        }
        const attempt = await recordExamModelScore(attemptId, item.position, newGrade.attempt_id)
        if (active) {
          onScored(attempt)
          setGrading(false)
        }
      })
      .catch(reason => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason))
          setGrading(false)
        }
      })
    return () => { active = false }
  }, [attemptId, baseline, grading, item.entry_id, item.position, onScored, thread.isStreaming, thread.messages, thread.sessionId])

  async function grade() {
    if (grading || thread.isStreaming) return
    setError('')
    try {
      const history = await getPracticeScoreHistory(item.entry_id)
      setBaseline(history.items.map(score => score.attempt_id))
      setGrading(true)
      controller.sendMessage({
        questionKey: key,
        content: `Оцени моё решение по подтверждённым критериям ОГЭ. Мой ответ:\n\n${item.answer ?? ''}`,
        attachments: [],
        language: 'ru',
        questionNotebookReferences: [item.entry_id],
      })
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason))
    }
  }

  return (
    <article className="rounded-xl border border-border p-4">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="text-sm font-semibold">Позиция {item.position} · {item.max_score} балла</p>
          <p className="mt-2 whitespace-pre-wrap text-sm">{item.answer}</p>
        </div>
        {item.earned_score !== null ? (
          <span className="shrink-0 text-sm font-semibold">{item.earned_score} / {item.max_score}</span>
        ) : (
          <button type="button" onClick={() => void grade()} disabled={grading || thread.isStreaming} className="shrink-0 rounded-lg border border-border px-3 py-2 text-xs disabled:opacity-50">
            {grading || thread.isStreaming ? 'Проверяю…' : 'Оценить решение'}
          </button>
        )}
      </div>
      {thread.messages.filter(message => message.role === 'assistant').map((message, index) => (
        <p key={`${key}:${index}`} className="mt-3 whitespace-pre-wrap text-sm text-muted-foreground">{message.content}</p>
      ))}
      {(error || thread.error) && <p role="alert" className="mt-3 text-sm text-destructive">{error || thread.error}</p>}
      {item.question.criteria?.length ? (
        <details className="mt-3 text-xs text-muted-foreground">
          <summary className="cursor-pointer">Критерии оценки</summary>
          <ul className="mt-2 list-disc pl-5">
            {item.question.criteria.map(criterion => <li key={`${criterion.score}:${criterion.text}`}>{criterion.score}: {criterion.text}</li>)}
          </ul>
        </details>
      ) : null}
    </article>
  )
}
