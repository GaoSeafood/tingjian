import { useRef, useState } from 'react'
import { ArrowRight, AudioLines, ChevronRight, CircleHelp, Download, FileUp, Link2, LoaderCircle, Video, X, FileText } from 'lucide-react'
import { api } from './api'
import { HelpDialog } from './brand'

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
  const [batch, setBatch] = useState(false)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [help, setHelp] = useState(false)
  const fileRef = useRef(null)
  const submitting = useRef(false)
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
      if (download) id = (await api.download(input)).id
      else if (file) id = (await api.upload(file)).id
      else if (batch) {
        const urls = input.split(/\r?\n/).map(value => value.trim()).filter(Boolean)
        const result = await api.batch(urls, 'prefer_subtitles')
        id = result.tasks[0]?.id
        if (!id) throw new Error(en ? 'No tasks were created. Please check your links.' : '未创建任务，请检查链接后重试。')
      } else id = (await api.url(input, 'prefer_subtitles')).id
      await refresh(); onOpen(id)
    } catch (err) { setError(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const recent = tasks.filter(task => (task.task_kind === 'download') === download).slice(0, 3)
  return <main className="miji-home">
    <div className="workspace-topbar"><b>{download ? (en ? 'Video downloads' : '视频下载') : (en ? 'Workspace' : '工作台')}</b><button onClick={() => setHelp(true)}><CircleHelp size={20}/>{en ? 'Help' : '帮助'}</button></div>
    <div className="workspace-content">
      <section className="workspace-hero">
        <div><h1>{download ? <>{en ? 'Keep the clips.' : '好素材，'}<br/>{en ? 'Create something new.' : '留给下一次灵感。'}</> : <>{en ? 'Listen closely.' : '把声音，'}<br/>{en ? 'Make it yours.' : '变成好内容。'}</>}</h1>
          <p>{download ? (en ? 'Paste a public video link to create a separate download task.' : '粘贴公开视频链接，单独保存你需要的视频素材。') : (en ? 'Upload your media, or paste a link. Your next idea starts here.' : '上传音视频，或粘贴链接，开始整理你的下一份灵感。')}</p>
        </div>
        <img className="workspace-mascot" src="/brand/miji-listening.png" alt="" width="1200" height="800" fetchPriority="high"/>
      </section>
      <form className="workspace-create" onSubmit={submit}>
        <div className="workspace-input-heading"><h2>{en ? 'Add your media' : '添加音视频'}</h2><p>{download ? (en ? 'Paste a video link to download.' : '粘贴视频链接，单独下载原视频。') : (en ? 'Paste a link, choose a file, or drop it here.' : '粘贴链接、上传文件，或直接把文件拖到这里。')}</p></div>
        <div className={`workspace-input workspace-unified ${drag ? 'is-dragging' : ''} ${file ? 'has-file' : ''}`}
          onDragOver={event => { event.preventDefault(); if (!download && !busy) setDrag(true) }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDrag(false) }}
          onDrop={event => { event.preventDefault(); setDrag(false); if (!download) choose(event.dataTransfer.files[0]); else if (event.dataTransfer.files.length) setError(en ? 'Paste a video link to download.' : '下载模式请粘贴视频链接或分享文案。') }}>
          <label className="sr-only" htmlFor="media-link">{download ? (en ? 'Video link' : '视频链接') : (en ? 'Video link or sharing text' : '视频链接或分享文案')}</label>
          <div className="workspace-unified-field">
            <span className="unified-source-icon">{file ? (file.type.startsWith('audio/') ? <AudioLines size={24}/> : <Video size={24}/>) : <Link2 size={24}/>}</span>
            <textarea id="media-link" value={file ? file.name : input} readOnly={!!file} disabled={busy} onChange={event => { setInput(event.target.value); setFile(null); setError('') }} rows={batch && !file ? 3 : 1}
              onPaste={event => { if (file && !busy) { const text = event.clipboardData.getData('text'); if (text.trim()) { event.preventDefault(); setFile(null); setInput(text); setError('') } } }}
              onKeyDown={event => { if (event.key === 'Enter' && (!batch || file) && !event.nativeEvent.isComposing) { event.preventDefault(); if (!busy && (file || input.trim())) event.currentTarget.form.requestSubmit() } }}
              placeholder={batch ? (en ? 'One video link per line, up to 20 links' : '每行粘贴一个视频链接，最多 20 条') : (en ? 'Paste a video link or sharing text…' : '粘贴视频链接或整段分享文案…')}/>
            {file && <button type="button" className="unified-remove-file" disabled={busy} aria-label={en ? 'Remove selected file' : '移除已选文件'} onClick={() => { setFile(null); setError('') }}><X size={18}/></button>}
          </div>
          <div className="workspace-unified-actions">
            {!download && <button type="button" className="outline unified-upload" disabled={busy} onClick={() => fileRef.current?.click()}><FileUp size={18}/>{en ? 'Upload file' : '上传文件'}</button>}
            <button type="submit" className="primary workspace-submit" disabled={busy || (!file && !input.trim())}>{busy ? <LoaderCircle className="spin" size={18}/> : download ? <Download size={18}/> : null}{busy ? (en ? 'Submitting…' : '正在提交…') : download ? (en ? 'Start download' : '开始下载') : (en ? 'Start transcription' : '开始听写')}<ArrowRight size={18}/></button>
          </div>
          <input ref={fileRef} type="file" accept="audio/*,video/*,.mkv,.webm,.m4a,.flac,.ogg" hidden disabled={busy || download} aria-label={en ? 'Choose audio or video' : '选择音视频文件'} onChange={event => { choose(event.target.files[0]); event.target.value = '' }}/>
        </div>
        {!download && <div className="workspace-input-options"><div className="link-options"><label><input type="checkbox" checked={batch} disabled={busy || !!file} onChange={event => setBatch(event.target.checked)}/>{en ? 'Multiple links' : '批量听写'}</label></div><p className="workspace-form-note">{file ? `${sizeLabel(file.size)} · ${en ? 'File selected. Start transcription when ready.' : '文件已选好，点击开始听写后上传。'}` : (en ? 'Subtitles are used first; audio transcription starts only when no usable subtitles are available.' : '默认优先使用字幕，没有可用字幕时才进行语音听写。')}</p></div>}
        {download && <p className="workspace-form-note">{en ? 'Downloads only. Transcription does not start automatically.' : '只下载原视频，不会自动听写。原文件按保留策略自动清理。'}</p>}
        {error && <div className="error-line" role="alert">{error}</div>}
      </form>
      <section className="workspace-recent"><div className="workspace-section-title"><h2>{en ? 'Recent tasks' : '最近任务'}</h2><button onClick={onHistory}>{en ? 'View all' : '查看全部'}<ChevronRight size={17}/></button></div>
        <div className="recent-table" role="table" aria-label={en ? 'Recent tasks' : '最近任务'}><div className="recent-table-head" role="row"><span role="columnheader">{en ? 'File name' : '文件名称'}</span><span role="columnheader">{en ? 'Status' : '状态'}</span><span role="columnheader">{en ? 'Created' : '创建时间'}</span></div>
          {recent.length ? recent.map(task => <button className="recent-table-row" type="button" key={task.id} onClick={() => onOpen(task.id)} aria-label={`${en ? 'Open' : '打开'} ${task.title}`}><span className="recent-task-title">{task.task_kind === 'download' ? <Download size={20}/> : task.media_kind === 'audio' ? <AudioLines size={20}/> : <Video size={20}/>}<span>{task.title}</span></span><span>{renderStatus(task)}</span><time dateTime={task.created_at}>{taskDate(task.created_at, en)}</time></button>) : <div className="workspace-empty"><FileText size={25} strokeWidth={1.4}/><p>{en ? 'Your first good idea starts here.' : '第一份好内容，从这里开始。'}</p><span>{en ? 'Your tasks will appear here.' : '添加素材后，任务会显示在这里。'}</span></div>}
        </div>
      </section>
      <p className="workspace-retention"><FileText size={16}/>{en ? 'Transcripts stay. Source files are cleaned up according to the retention policy.' : '文稿保留，原文件按保留策略自动清理。'}</p>
    </div>
    <HelpDialog open={help} onClose={() => setHelp(false)} lang={lang}/>
  </main>
}
