'use client'

import { useEffect, useMemo, useState } from 'react'
import {
  describeGraphAnswerError,
  emptyGraphAnswer,
  emptyPiece,
  emptyPoint,
  GRAPH_KIND_LABELS,
  parseGraphAnswer,
  pointsNeeded,
  serializeGraphAnswer,
  type GraphAnswer,
  type GraphPiece,
  type GraphPieceKind,
} from '@/lib/graph-coordinates'

const KINDS = Object.keys(GRAPH_KIND_LABELS) as GraphPieceKind[]

/**
 * Position 22 of the OGE takes a graph, and the attempt stores one answer
 * string. The student describes the graph by coordinates here, and the parent
 * keeps the serialized text as the answer it already saves and sends for
 * grading. ``onChange`` also reports what blocks saving, so the parent can hold
 * the save button without repeating the validation.
 */
export default function GraphCoordinateInput({
  value,
  onChange,
  disabled = false,
}: {
  value: string
  onChange: (answer: string, error: string) => void
  disabled?: boolean
}) {
  const [answer, setAnswer] = useState<GraphAnswer>(
    () => parseGraphAnswer(value) ?? emptyGraphAnswer()
  )
  const error = useMemo(() => describeGraphAnswerError(answer), [answer])
  const text = useMemo(() => serializeGraphAnswer(answer), [answer])

  useEffect(() => {
    onChange(text, error)
  }, [error, onChange, text])

  function patchPiece(index: number, patch: Partial<GraphPiece>) {
    setAnswer(current => ({
      ...current,
      pieces: current.pieces.map((piece, at) => (at === index ? { ...piece, ...patch } : piece)),
    }))
  }

  function changeKind(index: number, kind: GraphPieceKind) {
    const piece = answer.pieces[index]
    const needed = pointsNeeded(kind)
    const points = Array.from({ length: needed }, (_, at) => piece.points[at] ?? emptyPoint())
    patchPiece(index, { kind, points })
  }

  function patchPoint(index: number, at: number, axis: 'x' | 'y', coordinate: string) {
    const points = answer.pieces[index].points.map((point, position) =>
      position === at ? { ...point, [axis]: coordinate } : point
    )
    patchPiece(index, { points })
  }

  function patchPunctured(at: number, axis: 'x' | 'y', coordinate: string) {
    setAnswer(current => ({
      ...current,
      punctured: current.punctured.map((point, position) =>
        position === at ? { ...point, [axis]: coordinate } : point
      ),
    }))
  }

  const field = 'h-10 w-24 rounded-lg border border-border bg-background px-2 text-sm'

  return (
    <section className="mt-6 space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-sm font-medium">График по точкам</h3>
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Как заполнить</summary>
          <ol className="mt-2 list-decimal space-y-1 pl-5">
            <li>Построй график на черновике. Упрости функцию и найди выколотые точки.</li>
            <li>Раздели график на участки. Участок — это одна прямая или одна кривая.</li>
            <li>Выбери тип участка: прямая, парабола или гипербола.</li>
            <li>Введи точки участка: для прямой — две, для кривой — три.</li>
            <li>Для параболы возьми вершину и две точки пересечения с осью x.</li>
            <li>Если участок не занимает всю ось x, укажи границы и отметь, входят ли они.</li>
            <li>Выколотая точка — та, где функция не определена.</li>
            <li>В последнем поле запиши значения параметра.</li>
          </ol>
          <p className="mt-2">
            Верный график без значений параметра — 1 балл. Верный график с верными
            значениями — 2 балла.
          </p>
        </details>
      </div>

      {answer.pieces.map((piece, index) => (
        <fieldset key={index} disabled={disabled} className="rounded-xl border border-border p-4">
          <legend className="px-1 text-xs text-muted-foreground">Участок {index + 1}</legend>
          <div className="flex flex-wrap items-center gap-3">
            <label className="text-sm">
              Тип
              <select
                value={piece.kind}
                onChange={event => changeKind(index, event.target.value as GraphPieceKind)}
                className="ml-2 h-10 rounded-lg border border-border bg-background px-2 text-sm"
              >
                {KINDS.map(kind => (
                  <option key={kind} value={kind}>{GRAPH_KIND_LABELS[kind]}</option>
                ))}
              </select>
            </label>
            {answer.pieces.length > 1 && (
              <button
                type="button"
                onClick={() => setAnswer(current => ({
                  ...current,
                  pieces: current.pieces.filter((_, at) => at !== index),
                }))}
                className="text-xs text-muted-foreground underline"
              >
                Убрать участок
              </button>
            )}
          </div>
          <div className="mt-3 flex flex-wrap gap-4">
            {piece.points.slice(0, pointsNeeded(piece.kind)).map((point, at) => (
              <div key={at} className="text-sm">
                <span className="block text-xs text-muted-foreground">Точка {at + 1}</span>
                <div className="mt-1 flex items-center gap-2">
                  <input
                    value={point.x}
                    inputMode="decimal"
                    aria-label={`Участок ${index + 1}, точка ${at + 1}, x`}
                    onChange={event => patchPoint(index, at, 'x', event.target.value)}
                    className={field}
                    placeholder="x"
                  />
                  <input
                    value={point.y}
                    inputMode="decimal"
                    aria-label={`Участок ${index + 1}, точка ${at + 1}, y`}
                    onChange={event => patchPoint(index, at, 'y', event.target.value)}
                    className={field}
                    placeholder="y"
                  />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-wrap items-center gap-4 text-sm">
            <label className="flex items-center gap-2">
              от x
              <input
                value={piece.fromX}
                inputMode="decimal"
                onChange={event => patchPiece(index, { fromX: event.target.value })}
                className={field}
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={piece.fromIncluded}
                disabled={!piece.fromX.trim()}
                onChange={event => patchPiece(index, { fromIncluded: event.target.checked })}
              />
              граница входит
            </label>
            <label className="flex items-center gap-2">
              до x
              <input
                value={piece.toX}
                inputMode="decimal"
                onChange={event => patchPiece(index, { toX: event.target.value })}
                className={field}
              />
            </label>
            <label className="flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={piece.toIncluded}
                disabled={!piece.toX.trim()}
                onChange={event => patchPiece(index, { toIncluded: event.target.checked })}
              />
              граница входит
            </label>
          </div>
        </fieldset>
      ))}

      <button
        type="button"
        disabled={disabled}
        onClick={() => setAnswer(current => ({ ...current, pieces: [...current.pieces, emptyPiece()] }))}
        className="rounded-lg border border-border px-3 py-2 text-xs"
      >
        Добавить участок
      </button>

      <fieldset disabled={disabled} className="rounded-xl border border-border p-4">
        <legend className="px-1 text-xs text-muted-foreground">Выколотые точки</legend>
        {answer.punctured.length === 0 && (
          <p className="text-xs text-muted-foreground">Пока не указаны.</p>
        )}
        <div className="flex flex-wrap gap-4">
          {answer.punctured.map((point, at) => (
            <div key={at} className="flex items-center gap-2">
              <input
                value={point.x}
                inputMode="decimal"
                aria-label={`Выколотая точка ${at + 1}, x`}
                onChange={event => patchPunctured(at, 'x', event.target.value)}
                className={field}
                placeholder="x"
              />
              <input
                value={point.y}
                inputMode="decimal"
                aria-label={`Выколотая точка ${at + 1}, y`}
                onChange={event => patchPunctured(at, 'y', event.target.value)}
                className={field}
                placeholder="y"
              />
              <button
                type="button"
                onClick={() => setAnswer(current => ({
                  ...current,
                  punctured: current.punctured.filter((_, position) => position !== at),
                }))}
                className="text-xs text-muted-foreground underline"
              >
                убрать
              </button>
            </div>
          ))}
        </div>
        <button
          type="button"
          onClick={() => setAnswer(current => ({
            ...current,
            punctured: [...current.punctured, emptyPoint()],
          }))}
          className="mt-3 rounded-lg border border-border px-3 py-2 text-xs"
        >
          Добавить выколотую точку
        </button>
      </fieldset>

      <label className="block text-sm font-medium">
        Значения параметра
        <input
          value={answer.parameter}
          disabled={disabled}
          onChange={event => setAnswer(current => ({ ...current, parameter: event.target.value }))}
          placeholder="например −2,25; −2"
          className="mt-2 h-11 w-full rounded-xl border border-border bg-background px-3 font-normal"
        />
      </label>

      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}

      <details className="text-xs text-muted-foreground">
        <summary className="cursor-pointer">Что уйдёт на проверку</summary>
        <pre className="mt-2 whitespace-pre-wrap">{text}</pre>
      </details>
    </section>
  )
}
