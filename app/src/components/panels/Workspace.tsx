import { useState, useCallback } from 'react'

interface WorkspaceProps {
  accent: string
}

interface DirEntry {
  name: string
  type: 'dir' | 'file'
  size: number
  modified: number
}

interface TreeNode {
  path: string
  entries: DirEntry[]
  expanded: boolean
  loading: boolean
  error: boolean
}

interface FileView {
  path: string
  content: string
  size: number
  truncated: boolean
}

const ROOT = '/root/workspace'

function pathJoin(dir: string, name: string): string {
  return dir.endsWith('/') ? dir + name : dir + '/' + name
}

function breadcrumbParts(path: string): string[] {
  const rel = path.startsWith(ROOT) ? path.slice(ROOT.length) : path
  const parts = rel.split('/').filter(Boolean)
  return ['workspace', ...parts]
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

const labelStyle: React.CSSProperties = {
  fontSize: 10,
  textTransform: 'uppercase',
  letterSpacing: '0.1em',
  color: 'var(--text-faint)',
}

export default function Workspace({ accent }: WorkspaceProps) {
  const [tree, setTree] = useState<Record<string, TreeNode>>({})
  const [rootEntries, setRootEntries] = useState<DirEntry[] | null>(null)
  const [rootLoading, setRootLoading] = useState(false)
  const [rootError, setRootError] = useState(false)
  const [fileView, setFileView] = useState<FileView | null>(null)
  const [fileLoading, setFileLoading] = useState(false)
  const [fileError, setFileError] = useState<string | null>(null)
  const [selectedPath, setSelectedPath] = useState<string | null>(null)

  // Fetch root on first render
  const fetchRoot = useCallback(() => {
    if (rootEntries !== null || rootLoading) return
    setRootLoading(true)
    setRootError(false)
    fetch(`/api/workspace/ls?path=${encodeURIComponent(ROOT)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json() as Promise<DirEntry[]>
      })
      .then((entries) => {
        setRootEntries(entries)
        setRootLoading(false)
      })
      .catch(() => {
        setRootError(true)
        setRootLoading(false)
      })
  }, [rootEntries, rootLoading])

  // Fetch a directory's children
  function fetchDir(path: string) {
    setTree((prev) => ({
      ...prev,
      [path]: { path, entries: prev[path]?.entries ?? [], expanded: true, loading: true, error: false },
    }))
    fetch(`/api/workspace/ls?path=${encodeURIComponent(path)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json() as Promise<DirEntry[]>
      })
      .then((entries) => {
        setTree((prev) => ({
          ...prev,
          [path]: { path, entries, expanded: true, loading: false, error: false },
        }))
      })
      .catch(() => {
        setTree((prev) => ({
          ...prev,
          [path]: { path, entries: [], expanded: true, loading: false, error: true },
        }))
      })
  }

  function toggleDir(path: string) {
    const node = tree[path]
    if (!node) {
      fetchDir(path)
    } else if (node.expanded) {
      setTree((prev) => ({ ...prev, [path]: { ...prev[path], expanded: false } }))
    } else if (node.entries.length > 0) {
      setTree((prev) => ({ ...prev, [path]: { ...prev[path], expanded: true } }))
    } else {
      fetchDir(path)
    }
  }

  function openFile(path: string) {
    setSelectedPath(path)
    setFileLoading(true)
    setFileError(null)
    setFileView(null)
    fetch(`/api/workspace/read?path=${encodeURIComponent(path)}`)
      .then((r) => {
        if (r.status === 415) return r.json().then((d: { detail: string }) => Promise.reject(d.detail))
        if (!r.ok) return r.json().then((d: { detail?: string }) => Promise.reject(d.detail ?? `Error ${r.status}`))
        return r.json() as Promise<FileView>
      })
      .then((data) => {
        setFileView(data)
        setFileLoading(false)
      })
      .catch((err: string) => {
        setFileError(typeof err === 'string' ? err : 'Failed to read file')
        setFileLoading(false)
      })
  }

  // Trigger root fetch if not loaded
  if (rootEntries === null && !rootLoading && !rootError) {
    fetchRoot()
  }

  function renderEntries(entries: DirEntry[], parentPath: string, depth: number) {
    return entries.map((entry) => {
      const entryPath = pathJoin(parentPath, entry.name)
      const isDir = entry.type === 'dir'
      const node = tree[entryPath]
      const isExpanded = isDir && node?.expanded === true
      const isSelected = entryPath === selectedPath

      return (
        <div key={entryPath}>
          <div
            onClick={() => (isDir ? toggleDir(entryPath) : openFile(entryPath))}
            className="flex items-center"
            style={{
              paddingLeft: 10 + depth * 16,
              paddingRight: 10,
              paddingTop: 5,
              paddingBottom: 5,
              borderRadius: 7,
              cursor: 'pointer',
              gap: 7,
              background: isSelected ? `color-mix(in oklab, ${accent} 14%, transparent)` : 'transparent',
              border: isSelected ? `1px solid color-mix(in oklab, ${accent} 28%, transparent)` : '1px solid transparent',
              marginBottom: 1,
            }}
            onMouseEnter={(e) => {
              if (!isSelected) e.currentTarget.style.background = 'rgba(255,255,255,0.04)'
            }}
            onMouseLeave={(e) => {
              if (!isSelected) e.currentTarget.style.background = 'transparent'
            }}
          >
            <span style={{ fontSize: 12, flexShrink: 0, color: isDir ? accent : '#8892a4', width: 14, textAlign: 'center' }}>
              {isDir ? (isExpanded ? '▾' : '▸') : '·'}
            </span>
            <span
              className="mono overflow-hidden text-ellipsis whitespace-nowrap flex-1"
              style={{ fontSize: 12, color: isSelected ? '#f0f2f8' : isDir ? '#c6cad8' : '#9298ab', minWidth: 0 }}
            >
              {entry.name}
            </span>
            {!isDir && (
              <span style={{ fontSize: 10, color: 'var(--text-faint)', flexShrink: 0 }}>{fmtSize(entry.size)}</span>
            )}
          </div>
          {isDir && isExpanded && (
            <div>
              {node?.loading && (
                <div style={{ paddingLeft: 10 + (depth + 1) * 16, fontSize: 11, color: 'var(--text-faint)', paddingTop: 3, paddingBottom: 3 }}>
                  loading…
                </div>
              )}
              {node?.error && (
                <div style={{ paddingLeft: 10 + (depth + 1) * 16, fontSize: 11, color: '#fb6f6f', paddingTop: 3, paddingBottom: 3 }}>
                  Error reading directory
                </div>
              )}
              {node && !node.loading && !node.error && node.entries.length === 0 && (
                <div style={{ paddingLeft: 10 + (depth + 1) * 16, fontSize: 11, color: 'var(--text-faint)', paddingTop: 3, paddingBottom: 3 }}>
                  empty
                </div>
              )}
              {node && !node.loading && renderEntries(node.entries, entryPath, depth + 1)}
            </div>
          )}
        </div>
      )
    })
  }

  const crumbs = breadcrumbParts(selectedPath ?? ROOT)

  return (
    <div className="flex flex-1 flex-col" style={{ minHeight: 0 }}>
      {/* Breadcrumb */}
      <div
        className="flex items-center flex-wrap"
        style={{ padding: '12px 22px', borderBottom: '1px solid var(--border)', gap: 4, flexShrink: 0 }}
      >
        {crumbs.map((part, i) => (
          <span key={i} className="flex items-center" style={{ gap: 4 }}>
            {i > 0 && <span style={{ color: 'var(--text-faint)', fontSize: 12 }}>/</span>}
            <span
              className="mono"
              style={{
                fontSize: 12,
                color: i === crumbs.length - 1 ? '#f0f2f8' : 'var(--text-faint)',
                fontWeight: i === crumbs.length - 1 ? 600 : 400,
              }}
            >
              {part}
            </span>
          </span>
        ))}
      </div>

      {/* Two-pane body */}
      <div className="flex flex-1" style={{ minHeight: 0 }}>
        {/* Left: tree */}
        <div
          style={{
            width: 260,
            flexShrink: 0,
            borderRight: '1px solid var(--border)',
            overflowY: 'auto',
            padding: '10px 8px',
          }}
        >
          <div style={{ ...labelStyle, padding: '0 10px', marginBottom: 8 }}>Files</div>
          {rootLoading && (
            <div style={{ padding: '8px 10px', fontSize: 12, color: 'var(--text-faint)' }}>Loading…</div>
          )}
          {rootError && (
            <div style={{ padding: '8px 10px', fontSize: 12, color: '#fb6f6f' }}>
              Could not load /root/workspace
            </div>
          )}
          {rootEntries !== null && renderEntries(rootEntries, ROOT, 0)}
        </div>

        {/* Right: file viewer */}
        <div className="flex flex-1 flex-col" style={{ minWidth: 0, minHeight: 0 }}>
          {!selectedPath && (
            <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-faint)', fontSize: 13 }}>
              Select a file to view its contents
            </div>
          )}
          {selectedPath && fileLoading && (
            <div className="flex flex-1 items-center justify-center" style={{ color: 'var(--text-faint)', fontSize: 13 }}>
              Loading…
            </div>
          )}
          {selectedPath && fileError && (
            <div className="flex flex-1 flex-col items-center justify-center" style={{ gap: 8 }}>
              <span style={{ fontSize: 13, color: '#fb6f6f' }}>{fileError === 'binary file' ? 'Binary file — preview not available' : fileError}</span>
              <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{selectedPath}</span>
            </div>
          )}
          {fileView && !fileLoading && (
            <div className="flex flex-1 flex-col" style={{ minHeight: 0 }}>
              <div
                className="flex items-center justify-between"
                style={{ padding: '10px 18px', borderBottom: '1px solid var(--border)', flexShrink: 0, gap: 12 }}
              >
                <span className="mono overflow-hidden text-ellipsis whitespace-nowrap" style={{ fontSize: 12, color: '#9298ab', minWidth: 0 }}>
                  {fileView.path}
                </span>
                <div className="flex items-center" style={{ gap: 10, flexShrink: 0 }}>
                  <span style={{ fontSize: 11, color: 'var(--text-faint)' }}>{fmtSize(fileView.size)}</span>
                  {fileView.truncated && (
                    <span
                      style={{
                        fontSize: 10,
                        color: '#f59e0b',
                        background: 'rgba(245,158,11,0.12)',
                        border: '1px solid rgba(245,158,11,0.3)',
                        borderRadius: 5,
                        padding: '2px 7px',
                      }}
                    >
                      truncated
                    </span>
                  )}
                </div>
              </div>
              <pre
                style={{
                  flex: 1,
                  margin: 0,
                  padding: '16px 20px',
                  overflowY: 'auto',
                  overflowX: 'auto',
                  fontFamily: 'var(--font-mono, "IBM Plex Mono", monospace)',
                  fontSize: 12.5,
                  lineHeight: 1.65,
                  color: '#c8cdd8',
                  background: 'transparent',
                  whiteSpace: 'pre',
                  minHeight: 0,
                  tabSize: 2,
                }}
              >
                {fileView.content}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
