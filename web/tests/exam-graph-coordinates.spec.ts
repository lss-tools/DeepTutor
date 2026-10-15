import { describe, expect, it } from 'vitest'

import {
  describeGraphAnswerError,
  emptyGraphAnswer,
  emptyPiece,
  parseGraphAnswer,
  pointsNeeded,
  serializeGraphAnswer,
  type GraphAnswer,
} from '@/lib/graph-coordinates'

/** Task 13253 of the bank: a parabola with one punctured point, answer −2,25; −2. */
function bankAnswer(): GraphAnswer {
  return {
    pieces: [{
      ...emptyPiece('parabola'),
      points: [{ x: '-4', y: '0' }, { x: '-2,5', y: '-2,25' }, { x: '-1', y: '0' }],
    }],
    punctured: [{ x: '-3', y: '-2' }],
    parameter: '-2,25; -2',
  }
}

describe('graph coordinates answer', () => {
  it('serializes pieces, punctured points and parameter values', () => {
    expect(serializeGraphAnswer(bankAnswer())).toBe([
      'График:',
      '1) парабола через (−4; 0), (−2,5; −2,25), (−1; 0)',
      'Выколотые точки: (−3; −2)',
      'Значения параметра: −2,25; −2',
    ].join('\n'))
  })

  it('writes the bounds of a piece with its own inclusion signs', () => {
    const answer: GraphAnswer = {
      pieces: [
        { ...emptyPiece('parabola'), points: [{ x: '-1', y: '0' }, { x: '1', y: '4' }, { x: '3', y: '0' }], fromX: '-1', fromIncluded: true },
        { ...emptyPiece('line'), points: [{ x: '-2', y: '1' }, { x: '-3', y: '2' }], toX: '-1', toIncluded: false },
      ],
      punctured: [],
      parameter: '',
    }
    expect(serializeGraphAnswer(answer)).toBe([
      'График:',
      '1) парабола через (−1; 0), (1; 4), (3; 0), при x ≥ −1',
      '2) прямая через (−2; 1), (−3; 2), при x < −1',
      'Выколотых точек нет.',
      'Значения параметра: не указаны.',
    ].join('\n'))
  })

  it('reads its own text back without losing anything', () => {
    const text = serializeGraphAnswer(bankAnswer())
    const parsed = parseGraphAnswer(text)
    expect(parsed).not.toBeNull()
    expect(serializeGraphAnswer(parsed as GraphAnswer)).toBe(text)
    expect(parsed?.pieces[0].kind).toBe('parabola')
    expect(parsed?.punctured).toEqual([{ x: '−3', y: '−2' }])
    expect(parsed?.parameter).toBe('−2,25; −2')
  })

  it('restores both bounds and their inclusion', () => {
    const answer: GraphAnswer = {
      pieces: [{
        ...emptyPiece('line'),
        points: [{ x: '2', y: '1' }, { x: '3', y: '4' }],
        fromX: '2', fromIncluded: false, toX: '3', toIncluded: true,
      }],
      punctured: [],
      parameter: '',
    }
    const parsed = parseGraphAnswer(serializeGraphAnswer(answer))
    expect(parsed?.pieces[0]).toMatchObject({
      fromX: '2', fromIncluded: false, toX: '3', toIncluded: true,
    })
  })

  it('refuses text this editor did not write', () => {
    expect(parseGraphAnswer('Ответ: m = −2')).toBeNull()
    expect(parseGraphAnswer('')).toBeNull()
    expect(parseGraphAnswer('График:\nВыколотых точек нет.')).toBeNull()
    expect(parseGraphAnswer('График:\n1) кубика через (1; 2)')).toBeNull()
  })

  it('needs two points for a line and three for a curve', () => {
    expect(pointsNeeded('line')).toBe(2)
    expect(pointsNeeded('parabola')).toBe(3)
    expect(pointsNeeded('hyperbola')).toBe(3)
  })

  it('blocks saving until every point of a piece is filled', () => {
    expect(describeGraphAnswerError(emptyGraphAnswer())).toContain('Участок 1')
    const partial: GraphAnswer = {
      pieces: [{ ...emptyPiece('line'), points: [{ x: '1', y: '2' }, { x: '', y: '' }] }],
      punctured: [],
      parameter: '',
    }
    expect(describeGraphAnswerError(partial)).toContain('2 точки')
  })

  it('refuses coordinates that are not numbers', () => {
    const wrong: GraphAnswer = {
      pieces: [{ ...emptyPiece('line'), points: [{ x: 'вершина', y: '2' }, { x: '3', y: '4' }] }],
      punctured: [],
      parameter: '',
    }
    expect(describeGraphAnswerError(wrong)).toContain('числа')
  })

  it('accepts a decimal comma and a typographic minus', () => {
    const answer: GraphAnswer = {
      pieces: [{ ...emptyPiece('line'), points: [{ x: '−2,5', y: '0,25' }, { x: '3', y: '4' }] }],
      punctured: [],
      parameter: '',
    }
    expect(describeGraphAnswerError(answer)).toBe('')
  })

  it('lets a correct graph be saved without parameter values', () => {
    const answer = bankAnswer()
    answer.parameter = ''
    expect(describeGraphAnswerError(answer)).toBe('')
    expect(serializeGraphAnswer(answer)).toContain('Значения параметра: не указаны.')
  })
})
