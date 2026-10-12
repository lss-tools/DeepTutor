'use client'

import Link from 'next/link'
import Markdown from '@/components/common/MarkdownRenderer'
import { LearningErrorState, LearningShell } from '@/components/learning/LearningShell'
import {
  answerExamPosition,
  completeExamAttempt,
  createExamAttempt,
  getExamAttempt,
  getExamReadiness,
  type ExamAttempt,
  type ExamReadiness,
} from '@/lib/practice-api'
import { useEffect, useMemo, useState } from 'react'

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
    <LearningShell title="Полный вариант ОГЭ" subtitle="Попытка сохраняется по мере ответов.">
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

      {!attempt && !resuming && readiness && (
        <section className="rounded-2xl border border-border bg-card p-5">
          <h2 className="font-semibold">
            {readiness.ready ? 'Вариант готов' : `Не хватает позиций: ${readiness.missing_positions.length}`}
          </h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Для сборки нужны задания с подтверждённым эталоном и автоматической проверкой.
          </p>
          {!readiness.ready && (
            <p className="mt-3 text-sm">Позиции: {readiness.missing_positions.join(', ')}</p>
          )}
          <button
            type="button"
            disabled={!readiness.ready || busy}
            onClick={() => void start()}
            className="mt-5 rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50"
          >
            {busy ? 'Создаю…' : 'Начать вариант'}
          </button>
        </section>
      )}

      {attempt && attempt.status === 'in_progress' && activeItem && (
        <section className="rounded-2xl border border-border bg-card p-5 sm:p-7">
          <div className="mb-5 flex items-center justify-between text-sm text-muted-foreground">
            <span>Позиция {activeItem.position} из {attempt.items.length}</span>
            <span>{attempt.items.filter(item => item.answered).length} ответов сохранено</span>
          </div>
          <progress
            className="mb-6 h-1.5 w-full accent-primary"
            max={attempt.items.length}
            value={attempt.items.filter(item => item.answered).length}
            aria-label="Ход выполнения варианта"
          />
          <div className="prose prose-sm max-w-none dark:prose-invert">
            <Markdown content={activeItem.question.question} />
          </div>
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
              <input
                value={answer}
                onChange={event => setAnswer(event.target.value)}
                className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-3"
              />
            </label>
          )}
          <div className="mt-6 flex flex-wrap gap-3">
            <button type="button" onClick={() => void saveAnswer()} disabled={busy} className="rounded-xl bg-primary px-4 py-2.5 text-sm text-primary-foreground disabled:opacity-50">
              Сохранить ответ
            </button>
            {attempt.items.every(item => item.answered) && (
              <button type="button" onClick={() => void finish()} disabled={busy || activeItem.answer !== answer} className="rounded-xl border border-border px-4 py-2.5 text-sm disabled:opacity-50">
                Завершить вариант
              </button>
            )}
            <button type="button" onClick={close} disabled={busy} className="rounded-xl px-4 py-2.5 text-sm text-muted-foreground">
              Выйти и продолжить позже
            </button>
          </div>
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
