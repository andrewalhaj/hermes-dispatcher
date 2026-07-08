import React from 'react'

/**
 * Lightweight zero-dependency Markdown renderer.
 *
 * Supports the subset that shows up in task bodies and tile copy:
 *   - fenced code blocks  ```lang ... ```
 *   - ATX headers         #, ##, ###  →  h3 / h4 / h5
 *   - unordered lists     - / * bullets
 *   - ordered lists       1. 2. 3.
 *   - inline code         `x`
 *   - bold                **x**
 *   - italic              *x* / _x_
 *   - links               [text](url)
 *
 * React escapes all text nodes, so this is XSS-safe (no dangerouslySetInnerHTML).
 */

let keySeq = 0
function nextKey(prefix: string): string {
  keySeq += 1
  return `${prefix}-${keySeq}`
}

/** Render inline spans: code, bold, italic, links. */
function renderInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  // Order matters: code first (so its contents aren't re-parsed), then links, bold, italic.
  const pattern =
    /(`[^`]+`)|(\[[^\]]+\]\([^)]+\))|(\*\*[^*]+\*\*)|(\*[^*]+\*)|(_[^_]+_)/g
  let last = 0
  let m: RegExpExecArray | null
  while ((m = pattern.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index))
    const tok = m[0]
    if (tok.startsWith('`')) {
      nodes.push(
        <code
          key={nextKey('code')}
          style={{
            fontFamily: 'var(--font-mono, ui-monospace, monospace)',
            fontSize: '0.88em',
            background: 'rgba(255,255,255,0.08)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 5,
            padding: '1px 5px',
          }}
        >
          {tok.slice(1, -1)}
        </code>,
      )
    } else if (tok.startsWith('[')) {
      const linkM = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(tok)
      if (linkM) {
        nodes.push(
          <a
            key={nextKey('a')}
            href={linkM[2]}
            target="_blank"
            rel="noopener noreferrer"
            style={{ color: 'var(--accent, #f6b73c)', textDecoration: 'underline' }}
          >
            {linkM[1]}
          </a>,
        )
      } else {
        nodes.push(tok)
      }
    } else if (tok.startsWith('**')) {
      nodes.push(
        <strong key={nextKey('b')} style={{ fontWeight: 600, color: 'var(--text-primary, #f4f6fb)' }}>
          {tok.slice(2, -2)}
        </strong>,
      )
    } else {
      // *italic* or _italic_
      nodes.push(
        <em key={nextKey('i')} style={{ fontStyle: 'italic' }}>
          {tok.slice(1, -1)}
        </em>,
      )
    }
    last = m.index + tok.length
  }
  if (last < text.length) nodes.push(text.slice(last))
  return nodes
}

interface MarkdownProps {
  text: string
  style?: React.CSSProperties
}

/** Block-level Markdown renderer. */
export default function Markdown({ text, style }: MarkdownProps) {
  const lines = (text ?? '').split('\n')
  const blocks: React.ReactNode[] = []

  let i = 0
  while (i < lines.length) {
    const line = lines[i]

    // Fenced code block
    const fence = /^\s*```(\w*)\s*$/.exec(line)
    if (fence) {
      const code: string[] = []
      i += 1
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        code.push(lines[i])
        i += 1
      }
      i += 1 // skip closing fence
      blocks.push(
        <pre
          key={nextKey('pre')}
          style={{
            fontFamily: 'var(--font-mono, ui-monospace, monospace)',
            fontSize: 12,
            lineHeight: 1.5,
            background: 'rgba(0,0,0,0.32)',
            border: '1px solid rgba(255,255,255,0.08)',
            borderRadius: 9,
            padding: '11px 13px',
            margin: '12px 0',
            overflowX: 'auto',
            color: '#cfd3e0',
          }}
        >
          <code>{code.join('\n')}</code>
        </pre>,
      )
      continue
    }

    // Headers
    const hdr = /^(#{1,6})\s+(.*)$/.exec(line)
    if (hdr) {
      const level = hdr[1].length
      const sizes: Record<number, number> = { 1: 18, 2: 16, 3: 15, 4: 14, 5: 13, 6: 12.5 }
      blocks.push(
        <div
          key={nextKey('h')}
          style={{
            fontFamily: 'var(--font-display, inherit)',
            fontWeight: 600,
            fontSize: sizes[level] ?? 14,
            color: 'var(--text-primary, #f4f6fb)',
            margin: '16px 0 6px',
            lineHeight: 1.3,
          }}
        >
          {renderInline(hdr[2])}
        </div>,
      )
      i += 1
      continue
    }

    // Unordered list
    if (/^\s*[-*]\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        const content = lines[i].replace(/^\s*[-*]\s+/, '')
        items.push(
          <li key={nextKey('li')} style={{ margin: '3px 0' }}>
            {renderInline(content)}
          </li>,
        )
        i += 1
      }
      blocks.push(
        <ul key={nextKey('ul')} style={{ margin: '8px 0', paddingLeft: 20, listStyle: 'disc' }}>
          {items}
        </ul>,
      )
      continue
    }

    // Ordered list
    if (/^\s*\d+\.\s+/.test(line)) {
      const items: React.ReactNode[] = []
      while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
        const content = lines[i].replace(/^\s*\d+\.\s+/, '')
        items.push(
          <li key={nextKey('li')} style={{ margin: '3px 0' }}>
            {renderInline(content)}
          </li>,
        )
        i += 1
      }
      blocks.push(
        <ol key={nextKey('ol')} style={{ margin: '8px 0', paddingLeft: 22, listStyle: 'decimal' }}>
          {items}
        </ol>,
      )
      continue
    }

    // Blank line → spacer (collapse consecutive blanks)
    if (line.trim() === '') {
      i += 1
      continue
    }

    // Paragraph: gather consecutive non-blank, non-special lines
    const para: string[] = []
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^\s*```/.test(lines[i]) &&
      !/^#{1,6}\s+/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i]) &&
      !/^\s*\d+\.\s+/.test(lines[i])
    ) {
      para.push(lines[i])
      i += 1
    }
    blocks.push(
      <p key={nextKey('p')} style={{ margin: '8px 0', lineHeight: 1.62 }}>
        {renderInline(para.join(' '))}
      </p>,
    )
  }

  return <div style={style}>{blocks}</div>
}
