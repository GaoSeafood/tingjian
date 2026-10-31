import { useRef, useState } from 'react'
import { ArrowRight, AudioLines, ChevronRight, CircleHelp, Download, FileUp, Link2, LoaderCircle, Video, X, FileText } from 'lucide-react'
import { api } from './api'
import { HelpDialog } from './brand'
import { extractMediaLinks } from './mediaLinks'

const sizeLabel = bytes => bytes < 1024 ** 2 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`
function taskDate(value, en) {
  if (!value) return '—'
  const date = new Date(value)
  const today = date.toDateString() === new Date().toDateString()
  return `${today ? (en ? 'Today ' : '今天 ') : date.toLocaleDateString(en ? 'en-US' : 'zh-CN', { month: 'numeric', day: 'numeric' }) + ' '}${date.toLocaleTimeString(en ? 'en-US' : 'zh-CN', { hour: '2-digit', minute: '2-digit', hour12: false })}`
}

export default function WorkspaceHome({ tasks, refresh, onOpen, onHistory, renderStatus, lang, kind = 'transcribe' }) {
  const en = lang === 'en'
  const download = kind === 'download'
  const [file, setFile] = useState(null)
  const [input, setInput] = useState('')
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [help, setHelp] = useState(false)
  const fileRef = useRef(null)
  const submitting = useRef(false)
  const urls = extractMediaLinks(input)
  const multipleLinks = !download && !file && urls.length > 1
  const choose = selected => {
    if (!selected || busy || download) return
    setFile(selected); setInput(''); setError('')
  }
  const submit = async event => {
    event.preventDefault()
    if (submitting.current || (!file && !input.trim())) return
    submitting.current = true; setBusy(true); setError('')
    try {
      let id
      if (download) {
        if (urls.length > 1) throw new Error(en ? 'Paste one video link at a time to download.' : '下载时请一次粘贴一个视频链接。')
        id = (await api.download(input)).id
      }
      else if (file) id = (await api.upload(file)).id
      else if (multipleLinks) {
        if (urls.length > 20) throw new Error(en ? 'Add up to 20 video links at a time.' : '一次最多处理 20 条视频链接，请分次提交。')
        const result = await api.batch(urls, 'prefer_subtitles')
        id = result.tasks[0]?.id
        if (!id) throw new Error(en ? 'No tasks were created. Please check your links.' : '未创建任务，请检查链接后重试。')
      } else id = (await api.url(input, 'prefer_subtitles')).id
      await refresh()
      if (multipleLinks) onHistory()
      else onOpen(id)
    } catch (err) { setError(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const recent = tasks.filter(task => (task.task_kind === 'download') === download).slice(0, 3)
  return <main className="miji-home">
    <div className="workspace-topbar"><b>{download ? (en ? 'Video downloads' : '视频下载') : (en ? 'Workspace' : '工作台')}</b><button onClick={() => setHelp(true)}><CircleHelp size={20}/>{en ? 'Help' : '帮助'}</button></div>
    <div className="workspace-content">
      <section className="workspace-hero">
        <div><h1>{download ? <>{en ? 'Keep the clips.' : '好素材，'}<br/>{en ? 'Create something new.' : '留给下一次灵感。'}</> : <>{en ? 'Turn video into' : '把视频，整理成'}<br/>{en ? 'usable copy.' : '可用文稿。'}</>}</h1>
          <p>{download ? (en ? 'Paste a public video link to create a separate download task.' : '粘贴公开视频链接，单独保存你需要的视频素材。') : (en ? 'Paste links or upload a file to start organizing your media.' : '粘贴链接或上传音视频，开始整理你的素材。')}</p>
        </div>
        <img className="workspace-mascot" src="/brand/miji-listening.png" alt="" width="1200" height="800" fetchPriority="high"/>
      </section>
      <form className="workspace-create" onSubmit={submit}>
        <div className="workspace-input-heading"><h2>{download ? (en ? 'Add a video link' : '添加视频链接') : (en ? 'Add your media' : '添加音视频')}</h2><p>{download ? (en ? 'Paste a video link to download.' : '粘贴视频链接，单独下载原视频。') : (en ? 'Paste a link, choose a file, or drop it here.' : '粘贴链接、上传文件，或直接把文件拖到这里。')}</p></div>
        <div className={`workspace-input workspace-unified ${drag ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={event => { event.preventDefault(); if (!download && !busy) setDrag(true) }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDrag(false) }}
          onDrop={event => { event.preventDefault(); setDrag(false); if (!download) choose(event.dataTransfer.files[0]); else if (event.dataTransfer.files.length) setError(en ? 'Paste a video link to download.' : '下载模式请粘贴视频链接或分享文案。') }}>
          <label className="sr-only" htmlFor="media-link">{download ? (en ? 'Video link' : '视频链接') : (en ? 'Video link or sharing text' : '视频链接或分享文案')}</label>
          <div className="workspace-unified-field">
            <span className="unified-source-icon">{file ? (file.type.startsWith('audio/') ? <AudioLines size={24}/> : <Video size={24}/>) : <Link2 size={24}/>}</span>
            <textarea id="media-link" value={file ? file.name : input} readOnly={!!file} disabled={busy} onChange={event => { setInput(event.target.value); setFile(null); setError('') }} rows={!file && (multipleLinks || input.includes('\n')) ? Math.min(6, Math.max(3, input.split('\n').length)) : 1}
              onPaste={event => { if (file && !busy) { const text = event.clipboardData.getData('text'); if (text.trim()) { event.preventDefault(); setFile(null); setInput(text); setError('') } } }}
              onKeyDown={event => { if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.nativeEvent.isComposing) { event.preventDefault(); if (!busy && (file || input.trim())) event.currentTarget.form.requestSubmit() } }}
              placeholder={download ? (en ? 'Paste a video link or sharing text…' : '粘贴视频链接或整段分享文案…') : (en ? 'Paste video links or sharing text, one or more links…' : '粘贴视频链接或分享文案，支持多个链接…')}/>
            {file && <button type="button" className="unified-remove-file" disabled={busy} aria-label={en ? 'Remove selected file' : '移除已选文件'} onClick={() => { setFile(null); setError('') }}><X size={18}/></button>}
          </div>
          <div className="workspace-unified-actions">
            {!download && <button type="button" className="outline unified-upload" disabled={busy} onClick={() => fileRef.current?.click()}><FileUp size={18}/>{en ? 'Upload file' : '上传文件'}</button>}
            <button type="submit" className="primary workspace-submit" disabled={busy || (!file && !input.trim())}>{busy ? <LoaderCircle className="spin" size={18}/> : download ? <Download size={18}/> : null}{busy ? (en ? 'Submitting…' : '正在提交…') : download ? (en ? 'Start download' : '开始下载') : (en ? 'Start transcription' : '开始听写')}<ArrowRight size={18}/></button>
          </div>
          <input ref={fileRef} type="file" accept="audio/*,video/*,.mkv,.webm,.m4a,.flac,.ogg" hidden disabled={busy || download} aria-label={en ? 'Choose audio or video' : '选择音视频文件'} onChange={event => { choose(event.target.files[0]); event.target.value = '' }}/>
        </div>
        {!download && file && <p className="workspace-form-note">{sizeLabel(file.size)} · {en ? 'File selected. Start transcription when ready.' : '文件已选好，点击开始听写后上传。'}</p>}
        {download && <p className="workspace-form-note">{en ? 'Downloads only. Transcription does not start automatically.' : '只下载原视频，不会自动听写。原文件按保留策略自动清理。'}</p>}
        {error && <div className="error-line" role="alert">{error}</div>}
      </form>
      <section className="workspace-recent"><div className="workspace-section-title"><h2>{download ? (en ? 'Recent downloads' : '最近下载') : (en ? 'Recent tasks' : '最近任务')}</h2><button onClick={onHistory}>{en ? 'View all' : '查看全部'}<ChevronRight size={17}/></button></div>
        <div className="recent-table" role="table" aria-label={download ? (en ? 'Recent downloads' : '最近下载') : (en ? 'Recent tasks' : '最近任务')}><div className="recent-table-head" role="row"><span role="columnheader">{en ? 'File name' : '文件名称'}</span><span role="columnheader">{en ? 'Status' : '状态'}</span><span role="columnheader">{en ? 'Created' : '创建时间'}</span></div>
          {recent.length ? recent.map(task => <button className="recent-table-row" type="button" key={task.id} onClick={() => onOpen(task.id)} aria-label={`${en ? 'Open' : '打开'} ${task.title}`}><span className="recent-task-title">{task.task_kind === 'download' ? <Download size={20}/> : task.media_kind === 'audio' ? <AudioLines size={20}/> : <Video size={20}/>}<span>{task.title}</span></span><span>{renderStatus(task)}</span><time dateTime={task.created_at}>{taskDate(task.created_at, en)}</time></button>) : <div className="workspace-empty">{download ? <Download size={25} strokeWidth={1.4}/> : <FileText size={25} strokeWidth={1.4}/>}<p>{download ? (en ? 'No downloads yet.' : '还没有下载记录。') : (en ? 'Your first good idea starts here.' : '第一份好内容，从这里开始。')}</p><span>{download ? (en ? 'Paste a video link above to get started.' : '在上方粘贴视频链接，开始保存素材。') : (en ? 'Your tasks will appear here.' : '添加素材后，任务会显示在这里。')}</span></div>}
        </div>
      </section>
      <p className="workspace-retention">{download ? <Download size={16}/> : <FileText size={16}/>}{download ? (en ? 'Download files are temporary. Save a copy before they are cleaned up.' : '下载的原视频按保留策略自动清理，请及时保存。') : (en ? 'Transcripts stay. Source files are cleaned up according to the retention policy.' : '文稿保留，原文件按保留策略自动清理。')}</p>
    </div>
    <HelpDialog open={help} onClose={() => setHelp(false)} lang={lang}/>
  </main>
}
