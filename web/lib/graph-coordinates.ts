/**
 * OGE position 22 asks the student to build a graph and name the parameter
 * values. The web attempt cannot take a drawing, so the student describes the
 * graph by coordinates: every piece carries its type and the points that define
 * it, plus the punctured points and the parameter values. Two points define a
 * line and three define a parabola or a hyperbola, so the grader can rebuild
 * each piece without guessing.
 *
 * The exam attempt stores one answer string, so these helpers serialize the
 * description into readable text and read it back when the student returns.
 */

export type GraphPieceKind = 'line' | 'parabola' | 'hyperbola'

export interface GraphPoint {
  x: string
  y: string
}

export interface GraphPiece {
  kind: GraphPieceKind
  points: GraphPoint[]
  fromX: string
  toX: string
  fromIncluded: boolean
  toIncluded: boolean
}

export interface GraphAnswer {
  pieces: GraphPiece[]
  punctured: GraphPoint[]
  parameter: string
}

export const GRAPH_KIND_LABELS: Record<GraphPieceKind, string> = {
  line: 'прямая',
  parabola: 'парабола',
  hyperbola: 'гипербола',
}

const KIND_BY_LABEL = new Map(
  Object.entries(GRAPH_KIND_LABELS).map(([kind, label]) => [label, kind as GraphPieceKind])
)

const HEADING = 'График:'
const PUNCTURED_PREFIX = 'Выколотые точки: '
const PUNCTURED_NONE = 'Выколотых точек нет.'
const PARAMETER_PREFIX = 'Значения параметра: '
const PARAMETER_NONE = 'Значения параметра: не указаны.'

const NUMBER = /^[-−+]?\d+(?:[.,]\d+)?$/
const PIECE_LINE = /^\d+\)\s*(прямая|парабола|гипербола)\s+через\s+(.+)$/
const POINT = /\(\s*([^;()]+?)\s*;\s*([^;()]+?)\s*\)/g
const BOUNDS_BOTH = /^(\S+)\s*(≤|<)\s*x\s*(≤|<)\s*(\S+)$/
const BOUNDS_FROM = /^x\s*(≥|>)\s*(\S+)$/
const BOUNDS_TO = /^x\s*(≤|<)\s*(\S+)$/

/** Points that define a piece: a line needs two, a curve needs three. */
export function pointsNeeded(kind: GraphPieceKind): number {
  return kind === 'line' ? 2 : 3
}

export function emptyPoint(): GraphPoint {
  return { x: '', y: '' }
}

export function emptyPiece(kind: GraphPieceKind = 'parabola'): GraphPiece {
  return {
    kind,
    points: Array.from({ length: pointsNeeded(kind) }, emptyPoint),
    fromX: '',
    toX: '',
    fromIncluded: true,
    toIncluded: true,
  }
}

export function emptyGraphAnswer(): GraphAnswer {
  return { pieces: [emptyPiece()], punctured: [], parameter: '' }
}

/** Keep the typed value but show the minus sign the task statements use. */
function display(value: string): string {
  return value.trim().replace(/^-/, '−')
}

/** The parameter field holds several values, so every minus there is a sign. */
function displayValues(value: string): string {
  return value.trim().replace(/-(?=[\d.,∞])/g, '−')
}

function isNumber(value: string): boolean {
  return NUMBER.test(value.trim())
}

function filledPoint(point: GraphPoint): boolean {
  return point.x.trim() !== '' || point.y.trim() !== ''
}

function pointText(point: GraphPoint): string {
  return `(${display(point.x)}; ${display(point.y)})`
}

function boundsText(piece: GraphPiece): string {
  const from = piece.fromX.trim()
  const to = piece.toX.trim()
  const toSign = piece.toIncluded ? '≤' : '<'
  if (from && to) {
    return `${display(from)} ${piece.fromIncluded ? '≤' : '<'} x ${toSign} ${display(to)}`
  }
  if (from) return `x ${piece.fromIncluded ? '≥' : '>'} ${display(from)}`
  if (to) return `x ${toSign} ${display(to)}`
  return ''
}

/** The answer string stored in the attempt and read by the grading model. */
export function serializeGraphAnswer(answer: GraphAnswer): string {
  const lines = [HEADING]
  answer.pieces.forEach((piece, index) => {
    const points = piece.points.filter(filledPoint).map(pointText).join(', ')
    const bounds = boundsText(piece)
    const tail = bounds ? `, при ${bounds}` : ''
    lines.push(`${index + 1}) ${GRAPH_KIND_LABELS[piece.kind]} через ${points}${tail}`)
  })
  const punctured = answer.punctured.filter(filledPoint)
  lines.push(
    punctured.length ? PUNCTURED_PREFIX + punctured.map(pointText).join(', ') : PUNCTURED_NONE
  )
  lines.push(
    answer.parameter.trim() ? PARAMETER_PREFIX + displayValues(answer.parameter) : PARAMETER_NONE
  )
  return lines.join('\n')
}

function parsePoints(text: string): GraphPoint[] {
  const points: GraphPoint[] = []
  for (const match of text.matchAll(POINT)) {
    points.push({ x: match[1].trim(), y: match[2].trim() })
  }
  return points
}

function parseBounds(text: string, piece: GraphPiece): boolean {
  const both = BOUNDS_BOTH.exec(text)
  if (both) {
    piece.fromX = both[1]
    piece.fromIncluded = both[2] === '≤'
    piece.toIncluded = both[3] === '≤'
    piece.toX = both[4]
    return true
  }
  const from = BOUNDS_FROM.exec(text)
  if (from) {
    piece.fromIncluded = from[1] === '≥'
    piece.fromX = from[2]
    return true
  }
  const to = BOUNDS_TO.exec(text)
  if (to) {
    piece.toIncluded = to[1] === '≤'
    piece.toX = to[2]
    return true
  }
  return false
}

/**
 * Read a stored answer back into the editor. Returns null for anything this
 * editor did not write, so a resumed attempt falls back to plain text instead
 * of losing what the student typed.
 */
export function parseGraphAnswer(text: string): GraphAnswer | null {
  const lines = text.split(/\r?\n/).map(line => line.trim()).filter(Boolean)
  if (lines.shift() !== HEADING) return null
  const answer: GraphAnswer = { pieces: [], punctured: [], parameter: '' }
  for (const line of lines) {
    const piece = PIECE_LINE.exec(line)
    if (piece) {
      const kind = KIND_BY_LABEL.get(piece[1])
      if (!kind) return null
      const [pointsPart, boundsPart = ''] = piece[2].split(', при ')
      const parsed = emptyPiece(kind)
      const points = parsePoints(pointsPart)
      if (!points.length) return null
      parsed.points = points
      if (boundsPart && !parseBounds(boundsPart.trim(), parsed)) return null
      answer.pieces.push(parsed)
      continue
    }
    if (line === PUNCTURED_NONE) continue
    if (line.startsWith(PUNCTURED_PREFIX)) {
      const points = parsePoints(line.slice(PUNCTURED_PREFIX.length))
      if (!points.length) return null
      answer.punctured = points
      continue
    }
    if (line === PARAMETER_NONE) continue
    if (line.startsWith(PARAMETER_PREFIX)) {
      answer.parameter = line.slice(PARAMETER_PREFIX.length).trim()
      continue
    }
    return null
  }
  return answer.pieces.length ? answer : null
}

/**
 * What still blocks saving. The parameter values stay optional on purpose: the
 * criterion awards one point for a correct graph alone.
 */
export function describeGraphAnswerError(answer: GraphAnswer): string {
  if (!answer.pieces.length) return 'Добавьте хотя бы один участок графика.'
  for (const [index, piece] of answer.pieces.entries()) {
    const needed = pointsNeeded(piece.kind)
    const points = piece.points.slice(0, needed)
    if (points.some(point => !point.x.trim() || !point.y.trim())) {
      return `Участок ${index + 1}: заполните ${needed} ${needed === 2 ? 'точки' : 'точек'}.`
    }
    if (points.some(point => !isNumber(point.x) || !isNumber(point.y))) {
      return `Участок ${index + 1}: координаты — числа, например −2,25.`
    }
    for (const bound of [piece.fromX, piece.toX]) {
      if (bound.trim() && !isNumber(bound)) {
        return `Участок ${index + 1}: граница по x — число.`
      }
    }
  }
  for (const [index, point] of answer.punctured.entries()) {
    if (!filledPoint(point)) continue
    if (!point.x.trim() || !point.y.trim()) {
      return `Выколотая точка ${index + 1}: заполните обе координаты.`
    }
    if (!isNumber(point.x) || !isNumber(point.y)) {
      return `Выколотая точка ${index + 1}: координаты — числа.`
    }
  }
  return ''
}
