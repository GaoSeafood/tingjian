import { useState } from 'react'
import { api } from './api'

const LABELS = { rewrite: '改写稿', summary: '摘要', translate: '译文', highlights: '精彩片段', visual: '画面分析', answer: '视频问答' }

export default function WorkspaceHistory({ taskId, disabled, onRestore }) {
  const [open, setOpen] = useState(false)
  const [versions, setVersions] = useState([])
  const [selected, setSelected] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const toggle = async () => {
    if (open) { setOpen(false); return }
    setOpen(true); setBusy(true); setError('')
    try { setVersions(await api.versions(taskId)); setSelected(null) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const inspect = async id => {
    setBusy(true); setError('')
    try { setSelected(await api.version(taskId, id)) }
    catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  const restore = async () => {
    setBusy(true); setError('')
    try {
      await api.restoreVersion(taskId, selected.id)
      await onRestore(selected.kind)
      setVersions(await api.versions(taskId)); setSelected(null)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <section className="workspace-history">
    <button type="button" className="outline compact" onClick={toggle}>{open ? '收起版本记录' : '版本记录'}</button>
    {open && <div className="version-browser">
      <p>重新生成会保留旧版本。恢复会另存一版，不会删除历史。</p>
      {error && <div className="error-line" role="alert">{error}</div>}
      <select aria-label="选择历史版本" disabled={busy} value={selected?.id || ''} onChange={e => e.target.value && inspect(e.target.value)}>
        <option value="">{busy ? '正在读取…' : versions.length ? '选择要查看的版本' : '暂时没有版本记录'}</option>
        {versions.map(v => <option key={v.id} value={v.id}>{LABELS[v.kind] || v.kind} · {new Date(v.created_at).toLocaleString()} · {v.origin === 'edited' ? '手动编辑' : v.origin === 'restored' ? '恢复' : '生成'} · 原稿 v{v.source_revision}</option>)}
      </select>
      {selected && <div className="version-preview"><pre>{typeof selected.content.value === 'string' ? selected.content.value : JSON.stringify(selected.content.value, null, 2)}</pre>
        {selected.kind !== 'answer' && <button type="button" className="outline compact" disabled={busy || disabled} onClick={restore}>恢复这个版本</button>}
      </div>}
    </div>}
  </section>
}
