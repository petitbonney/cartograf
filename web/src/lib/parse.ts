import { CORE_SCHEMA, load } from 'js-yaml'
import type { Cartography } from './types'

export class ParseError extends Error {}

/**
 * Parse cartograf output (YAML or JSON) into a Cartography object.
 *
 * YAML uses the core schema: no timestamp or merge-key magic, so dates and
 * versions stay strings exactly as written (the tool quotes them anyway).
 */
export function parseCartography(text: string, name = 'file'): Cartography {
  const trimmed = text.trimStart()
  if (!trimmed) throw new ParseError(`${name} is empty`)
  if (trimmed.startsWith('<')) {
    throw new ParseError(`${name} looks like an HTML page, not a cartograf output file`)
  }

  let data: unknown
  try {
    data = trimmed.startsWith('{') ? JSON.parse(text) : load(text, { schema: CORE_SCHEMA })
  } catch (err) {
    throw new ParseError(`${name} could not be parsed: ${(err as Error).message.split('\n')[0]}`)
  }

  if (!isObject(data) || !isObject(data.repos)) {
    throw new ParseError(`${name} is not a cartograf output file (no "repos" section)`)
  }
  return {
    meta: isObject(data.meta) ? data.meta : {},
    frameworks: isObject(data.frameworks) ? (data.frameworks as Cartography['frameworks']) : {},
    repos: data.repos as Cartography['repos'],
    review: Array.isArray(data.review) ? (data.review as Cartography['review']) : [],
  }
}

function isObject(v: unknown): v is Record<string, any> {
  return typeof v === 'object' && v !== null && !Array.isArray(v)
}
