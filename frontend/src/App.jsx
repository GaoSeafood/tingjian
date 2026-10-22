import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, AudioLines, Check, ChevronRight, Clock3, Copy, Download, ExternalLink, Film, Video, Crown,
  History, Link2, LoaderCircle, LockKeyhole, LogOut, PencilLine,
  Play, RotateCcw, Search, Sparkles, Trash2, Upload, UserRound, Volume2, WandSparkles, X,
  SlidersHorizontal, Save, Languages, ChevronDown, KeyRound, Layers3, Sun, Moon, Monitor,
} from 'lucide-react'
import { api } from './api'

const COPY = {
  zh: {
    workspace: '工作台', history: '历史记录', membership: '会员', language: '简体中文', appearance: '外观', themeLight: '浅色', themeDark: '深色', themeSystem: '跟随系统', service: '听写服务可用', private: '仅你可访问',
    admin: '管理员', member: '个人账号', accountSettings: '账户设置', accountBenefits: '账号权益', apiSettings: 'API 设置', signOut: '退出登录',
    overview: '任务概览', taskCount: '已创建任务', accountNote: '你的任务和文案仅自己可见。',
    transcriptionQuota: '本月听写额度', remaining: '剩余', unlimited: '不限量', monthly: '月',
    eyebrow: '视频内容工作台', heroOne: '让视频内容', heroTwo: '听得清，也用得上',
    intro: '粘贴视频链接或上传本地素材，快速提取可编辑文案。完成听写后，再决定是否分析画面、提炼亮点或改写脚本。',
    transcribe: '听写文案', downloadVideo: '下载视频', pasteVideo: '粘贴视频链接或整段分享文案…', pasteDownload: '粘贴要下载的视频链接或分享文案…',
    upload: '上传文件', start: '开始听写', startDownload: '开始下载', submitting: '正在提交…', parsing: '正在解析…',
    hintTranscribe: '支持 MP4、MOV、MKV、WebM、MP3、WAV、M4A，单个文件最大 2GB。',
    hintDownload: '只下载原视频，不会自动听写；服务器临时文件保留 24 小时。', hintFile: '确认文件无误后再开始听写，文件不会提前上传。',
    platforms: '支持常见视频链接', localMedia: '本地视频和音频',
    benefit1: '先听写，后处理', benefit2: '私人工作台', benefit3: '媒体临时保存，文案持续保留',
    recent: '最近任务', noTasks: '还没有任务记录，先粘贴视频链接或上传素材吧。',
    learnEyebrow: '从素材到可用内容', learnTitle: '一条工作流，完成视频内容整理',
    learnIntro: '把零散素材变成可检索、可编辑、可继续创作的内容。每一步由你决定，听写之外的 AI 处理不会自动启动。',
    feature1Title: '提取视频文案', feature1: '粘贴公开视频链接或上传本地音视频，生成可编辑听写稿。复制文案，或导出 TXT、SRT。',
    feature2Title: '整理视频素材', feature2: '需要保存原视频时，单独创建下载任务。媒体文件会按保留策略清理，任务文案保留在历史记录。',
    feature3Title: '继续分析与创作', feature3: '听写完成后，可主动找亮点、分析画面或按新主题改写脚本，逐步把素材变成创作参考。',
    step1: '添加素材', step2: '检查并编辑听写稿', step3: '选择后续处理',
    pageEnd: '先把内容听清，再决定怎样使用。',
  },
  en: {
    workspace: 'Workspace', history: 'History', membership: 'Plans', language: 'English', appearance: 'Appearance', themeLight: 'Light', themeDark: 'Dark', themeSystem: 'System', service: 'Transcription ready', private: 'Private workspace',
    admin: 'Admin', member: 'Personal account', accountSettings: 'Account settings', accountBenefits: 'Account benefits', apiSettings: 'API settings', signOut: 'Sign out',
    overview: 'Task overview', taskCount: 'Tasks created', accountNote: 'Your tasks and transcripts are visible only to you.',
    transcriptionQuota: 'Monthly transcription quota', remaining: 'Remaining', unlimited: 'Unlimited', monthly: 'mo',
    eyebrow: 'VIDEO CONTENT WORKSPACE', heroOne: 'Make video content', heroTwo: 'clear to hear, ready to use',
    intro: 'Paste a video link or upload a local file to create an editable transcript. Then choose whether to analyze visuals, find highlights, or rewrite the script.',
    transcribe: 'Transcribe', downloadVideo: 'Download video', pasteVideo: 'Paste a video link or sharing text…', pasteDownload: 'Paste a video link or sharing text to download…',
    upload: 'Upload file', start: 'Start transcription', startDownload: 'Start download', submitting: 'Submitting…', parsing: 'Resolving link…',
    hintTranscribe: 'MP4, MOV, MKV, WebM, MP3, WAV, M4A · up to 2 GB per file.',
    hintDownload: 'Downloads the source video only. Temporary media is kept for 24 hours.', hintFile: 'Review the selected file before starting. It has not been uploaded yet.',
    platforms: 'Works with common video links', localMedia: 'Local video and audio',
    benefit1: 'Transcribe first, process later', benefit2: 'Private workspace', benefit3: 'Temporary media, transcripts retained',
    recent: 'Recent tasks', noTasks: 'No tasks yet. Paste a video link or upload a file to get started.',
    learnEyebrow: 'FROM MEDIA TO USEFUL CONTENT', learnTitle: 'One workflow for organizing video content',
    learnIntro: 'Turn scattered media into content you can search, edit, and build on. You choose every step; AI tools beyond transcription never run automatically.',
    feature1Title: 'Extract a transcript', feature1: 'Paste a public video link or upload audio/video to create an editable transcript. Copy it or export TXT and SRT.',
    feature2Title: 'Organize video assets', feature2: 'Create a separate download task when you need the source video. Media is cleaned up by its retention policy while task transcripts remain in history.',
    feature3Title: 'Analyze and create', feature3: 'After transcription, choose to find highlights, analyze visuals, or rewrite the script for a new topic.',
    step1: 'Add media', step2: 'Review and edit', step3: 'Choose what to do next',
    pageEnd: 'Hear the content clearly, then decide how to use it.',
  },
}
const tr = (lang, key) => COPY[lang]?.[key] || COPY.zh[key] || key

const STATUS = {
  queued: '等待中', preparing: '准备中', downloading: '下载中', transcribing: '听写中',
  completed: '已完成', failed: '失败',
}

const ACTIVE_TASK_STATUSES = ['queued', 'preparing', 'downloading', 'transcribing']

function taskDisplayProgress(task, now = Date.now()) {
  if (!task) return 0
  const reported = Math.max(0, Math.min(100, Number(task.progress) || 0))
  if (task.task_kind === 'download') return task.status === 'completed' ? 100 : reported
  if (task.status === 'completed') {
    const finishedAt = Date.parse(task.updated_at || '')
    if (!Number.isFinite(finishedAt)) return 100
    return Math.min(100, 90 + Math.max(0, now - finishedAt) / 400)
  }
  if (task.status === 'failed') return reported
  const createdAt = Date.parse(task.created_at || '')
  const elapsedSeconds = Number.isFinite(createdAt) ? Math.max(0, (now - createdAt) / 1000) : 0
  // Smoothly approaches 90% while the server works. The persisted timestamp
  // makes the same task show the same progress after navigation or a reload.
  return Math.min(90, 1 + 89 * (1 - Math.exp(-elapsedSeconds / 42)))
}

function useTaskDisplayProgress(task) {
  const [now, setNow] = useState(Date.now())
  useEffect(() => {
    if (!task) return
    const isActive = ACTIVE_TASK_STATUSES.includes(task.status)
    const isSettling = task.status === 'completed' && task.task_kind !== 'download' && taskDisplayProgress(task) < 100
    if (!isActive && !isSettling) return
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [task?.id, task?.status, task?.task_kind, task?.created_at, task?.updated_at])
  return taskDisplayProgress(task, now)
}

function Logo() {
  return <div className="logo"><span className="wave"><i/><i/><i/><i/><i/></span><strong>听见</strong></div>
}

function Header({ page, setPage, user, lang, theme, onThemeChange, onLanguageChange, onLogout, panelMode }) {
  const [accountOpen, setAccountOpen] = useState(false)
  const [languageOpen, setLanguageOpen] = useState(false)
  const [themeOpen, setThemeOpen] = useState(false)
  const [billing, setBilling] = useState(null)
  const accountRef = useRef(null)
  const languageRef = useRef(null)
  const themeRef = useRef(null)
  useEffect(() => {
    const dismiss = event => {
      if (!accountRef.current?.contains(event.target)) setAccountOpen(false)
      if (!languageRef.current?.contains(event.target)) setLanguageOpen(false)
      if (!themeRef.current?.contains(event.target)) setThemeOpen(false)
    }
    const escape = event => { if (event.key === 'Escape') { setAccountOpen(false); setLanguageOpen(false); setThemeOpen(false) } }
    document.addEventListener('pointerdown', dismiss)
    document.addEventListener('keydown', escape)
    return () => { document.removeEventListener('pointerdown', dismiss); document.removeEventListener('keydown', escape) }
  }, [])
  useEffect(() => {
    if (accountOpen) api.billing().then(setBilling).catch(() => setBilling(null))
  }, [accountOpen])
  const openPage = nextPage => { setPage(nextPage); setAccountOpen(false) }
  const quotaTotal = billing?.plan?.monthly_minutes
  const quotaUnlimited = billing?.unlimited || quotaTotal < 0
  const quotaRemaining = billing?.remaining_minutes
  const quotaProgress = quotaUnlimited || !quotaTotal ? 0 : Math.min(100, Math.max(0, billing.used_minutes / quotaTotal * 100))
  return <header className="header">
    <Logo />
    <nav>
      <button className={page === 'home' || page === 'detail' ? 'active' : ''} onClick={() => setPage('home')}>{tr(lang, 'workspace')}</button>
      <button className={page === 'history' ? 'active' : ''} onClick={() => setPage('history')}>{tr(lang, 'history')}</button>
      <button className={page === 'membership' ? 'active' : ''} onClick={() => setPage('membership')}>{tr(lang, 'membership')}</button>
      {panelMode && user?.role === 'admin' && <button className={page === 'admin' ? 'active' : ''} onClick={() => setPage('admin')}>{lang === 'en' ? 'Admin' : '管理后台'}</button>}
    </nav>
    <div className="account">
      <div className="theme-menu" ref={themeRef}>
        <button className="theme-trigger" aria-label={tr(lang, 'appearance')} title={tr(lang, 'appearance')} aria-expanded={themeOpen} onClick={() => { setThemeOpen(value => !value); setLanguageOpen(false); setAccountOpen(false) }}>
          {theme === 'dark' ? <Moon size={18}/> : theme === 'light' ? <Sun size={18}/> : <Monitor size={18}/>}
        </button>
        {themeOpen && <div className="theme-popover" role="menu" aria-label={tr(lang, 'appearance')}>
          {[
            ['light', Sun, tr(lang, 'themeLight')],
            ['dark', Moon, tr(lang, 'themeDark')],
            ['system', Monitor, tr(lang, 'themeSystem')],
          ].map(([value, Icon, label]) => <button key={value} role="menuitemradio" aria-checked={theme === value} className={theme === value ? 'selected' : ''} onClick={() => { onThemeChange(value); setThemeOpen(false) }}><Icon size={17}/><span>{label}</span>{theme === value && <Check size={15}/>}</button>)}
        </div>}
      </div>
      <div className="language-menu" ref={languageRef}>
        <button className="language-trigger" aria-expanded={languageOpen} onClick={() => { setLanguageOpen(value => !value); setAccountOpen(false); setThemeOpen(false) }}><Languages size={19}/><span>{tr(lang, 'language')}</span><ChevronDown size={15}/></button>
        {languageOpen && <div className="language-popover" role="menu"><button role="menuitem" className={lang === 'zh' ? 'selected' : ''} onClick={() => { onLanguageChange('zh'); setLanguageOpen(false) }}>简体中文{lang === 'zh' && <Check size={15}/>}</button><button role="menuitem" className={lang === 'en' ? 'selected' : ''} onClick={() => { onLanguageChange('en'); setLanguageOpen(false) }}>English{lang === 'en' && <Check size={15}/>}</button></div>}
      </div>
      <div className="account-menu" ref={accountRef}>
        <button className="account-trigger" aria-expanded={accountOpen} onClick={() => { setAccountOpen(value => !value); setLanguageOpen(false); setThemeOpen(false) }}>
          <span className="account-avatar">{(user?.username || 'U').slice(0,1).toUpperCase()}</span><span className="account-name">{user?.username}</span><ChevronDown size={16}/>
        </button>
        {accountOpen && <section className="account-popover" aria-label={tr(lang, 'accountSettings')}>
          <div className="account-identity"><b>{user?.username}</b><span>{user?.role === 'admin' ? tr(lang, 'admin') : tr(lang, 'member')}</span></div>
          <div className="account-usage"><strong>{tr(lang, 'transcriptionQuota')}</strong><div><span>{tr(lang, 'remaining')}</span><b>{quotaUnlimited ? tr(lang, 'unlimited') : quotaRemaining == null ? '—' : `${quotaRemaining} ${lang === 'en' ? 'min' : '分钟'}`}</b></div>{!quotaUnlimited && <div className="account-progress"><i style={{width: `${quotaProgress}%`}}/></div>}<small>{billing ? `${billing.plan.name} · ${billing.plan.monthly_minutes < 0 ? tr(lang, 'unlimited') : `${billing.used_minutes} / ${billing.plan.monthly_minutes} ${lang === 'en' ? 'min' : '分钟'}`}` : (lang === 'en' ? 'Loading usage…' : '正在读取用量…')}</small></div>
          <p className="account-note">{tr(lang, 'accountNote')}</p>
          {panelMode && user?.role === 'admin' && <button className="account-action account-action-accent" onClick={() => openPage('admin')}><SlidersHorizontal size={18}/>{lang === 'en' ? 'Admin console' : '管理后台'}</button>}
          <button className="account-action account-action-accent" onClick={() => openPage('benefits')}><UserRound size={18}/>{tr(lang, 'accountBenefits')}</button>
          {billing?.plan?.code?.startsWith('ultra_') && <button className="account-action" onClick={() => openPage('api-keys')}><KeyRound size={18}/>API Key</button>}
          <button className="account-action" onClick={() => openPage('settings')}><UserRound size={18}/>{tr(lang, 'accountSettings')}</button>
          <button className="account-action" onClick={() => openPage('history')}><History size={18}/>{tr(lang, 'history')}</button>
          <button className="account-action" onClick={() => openPage('membership')}><Crown size={18}/>{tr(lang, 'membership')}</button>
          <button className="account-action account-action-logout" onClick={() => { setAccountOpen(false); onLogout() }}><LogOut size={18}/>{tr(lang, 'signOut')}</button>
        </section>}
      </div>
    </div>
  </header>
}

function Login({ onLogin, lang, onLanguageChange }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async (event) => {
    event.preventDefault(); setBusy(true); setError('')
    try { await api.login(username, password); onLogin(await api.me()) }
    catch (err) { setError(err.message === 'UNAUTHORIZED' ? '用户名或密码错误' : err.message) }
    finally { setBusy(false) }
  }
  return <main className="login-page">
    <button className="login-language" onClick={() => onLanguageChange(lang === 'zh' ? 'en' : 'zh')}><Languages size={17}/>{tr(lang, 'language')}<ChevronDown size={15}/></button>
    <section className="login-panel">
      <Logo />
      <div><h1>{lang === 'en' ? 'Welcome back' : '欢迎回来'}</h1><p>{lang === 'en' ? 'Sign in to your private video workspace' : '登录你的私人视频听写工作台'}</p></div>
      <form onSubmit={submit}>
        <label>{lang === 'en' ? 'Username' : '用户名'}<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label>
        <label>{lang === 'en' ? 'Password' : '密码'}<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" autoFocus /></label>
        {error && <div className="error-line">{error}</div>}
        <button className="primary full" disabled={busy || !password}>{busy ? <LoaderCircle className="spin" size={18}/> : <LockKeyhole size={18}/>} {lang === 'en' ? 'Sign in' : '登录'}</button>
      </form>
    </section>
  </main>
}

function StatusMark({ task, lang = 'zh' }) {
  const progress = useTaskDisplayProgress(task)
  const label = (zh, en) => lang === 'en' ? en : zh
  if (task.status === 'completed') {
    if (task.task_kind !== 'download' && progress < 100) return <span className="status working"><LoaderCircle className="spin" size={15}/>{label('正在整理结果', 'Finalizing')} {Math.round(progress)}%</span>
    if (task.task_kind === 'download' && !task.source_available) return <span className="status">{label('文件已过期','File expired')}</span>
    return <span className="status success"><Check size={15}/>{task.task_kind === 'download' ? label('可下载','Ready') : label(STATUS[task.status], 'Completed')}</span>
  }
  if (task.status === 'failed') return <span className="status failed">{task.task_kind === 'download' ? label('下载失败','Download failed') : label('失败','Failed')}</span>
  const enStatus = {queued:'Queued', preparing:'Preparing', downloading:'Downloading', transcribing:'Transcribing'}
  if (ACTIVE_TASK_STATUSES.includes(task.status)) return <span className="status working"><LoaderCircle className="spin" size={15}/>{lang === 'en' ? enStatus[task.status] || 'Queued' : STATUS[task.status]} {Math.round(progress)}%</span>
  return <span className="status"><Clock3 size={15}/>{lang === 'en' ? ({queued:'Queued'}[task.status] || task.status) : STATUS[task.status] || task.status}</span>
}

function TaskTable({ tasks, onOpen, onDelete, full = false, lang = 'zh' }) {
  const [selectedIds, setSelectedIds] = useState(() => new Set())
  const taskIds = tasks.map(task => task.id)
  const allSelected = full && taskIds.length > 0 && taskIds.every(id => selectedIds.has(id))
  useEffect(() => {
    setSelectedIds(current => new Set([...current].filter(id => taskIds.includes(id))))
  }, [tasks])
  const remove = async (event, task) => {
    event.stopPropagation()
    if (!window.confirm(`确定删除“${task.title}”这条历史记录吗？听写稿、亮点和改写结果都会删除。`)) return
    try { await onDelete(task.id); setSelectedIds(current => { const next = new Set(current); next.delete(task.id); return next }) } catch (err) { window.alert(err.message) }
  }
  const toggleOne = (event, id) => {
    event.stopPropagation()
    setSelectedIds(current => { const next = new Set(current); next.has(id) ? next.delete(id) : next.add(id); return next })
  }
  const toggleAll = event => {
    event.stopPropagation()
    setSelectedIds(allSelected ? new Set() : new Set(taskIds))
  }
  const removeSelected = async () => {
    const ids = [...selectedIds].filter(id => taskIds.includes(id))
    if (!ids.length || !window.confirm(`确定删除选中的 ${ids.length} 条任务记录吗？关联的文案、结果和临时文件都会删除。`)) return
    try { await Promise.all(ids.map(id => onDelete(id))); setSelectedIds(new Set()) }
    catch (err) { window.alert(err.message) }
  }
  const recentTitle = lang === 'en' ? 'Recent tasks' : '最近任务'
  return <section className={`recent ${full ? 'history-list' : ''}`}>
    <div className="section-title"><h2>{full ? (lang === 'en' ? 'All task history' : '全部任务记录') : recentTitle}</h2>{full && <div className="history-actions"><span>{lang === 'en' ? `${tasks.length} items` : `${tasks.length} 条记录`}</span>{selectedIds.size > 0 && <button className="outline compact bulk-delete" onClick={removeSelected}><Trash2 size={15}/>{lang === 'en' ? `Delete selected (${selectedIds.size})` : `删除选中 (${selectedIds.size})`}</button>}</div>}</div>
    <div className={`task-table ${full ? 'selectable' : ''}`}>
      <div className="task-head">{full && <label className="task-select-cell" onClick={event => event.stopPropagation()}><input type="checkbox" checked={allSelected} onChange={toggleAll} aria-label={lang === 'en' ? 'Select all history' : '全选历史记录'}/></label>}<span>{lang === 'en' ? 'Title' : '标题'}</span><span>{lang === 'en' ? 'Source' : '来源'}</span><span>{lang === 'en' ? 'Length' : '时长'}</span><span>{lang === 'en' ? 'Status' : '状态'}</span><span>{lang === 'en' ? 'Date' : '时间'}</span><span/></div>
      {tasks.length === 0 && <div className="empty">{tr(lang, 'noTasks')}</div>}
      {tasks.map(task => <div className="task-row" role="button" tabIndex="0" key={task.id}
        onClick={() => onOpen(task.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') onOpen(task.id) }}>
        {full && <span className="task-select-cell" onClick={event => event.stopPropagation()}><input type="checkbox" checked={selectedIds.has(task.id)} onChange={event => toggleOne(event, task.id)} aria-label={`选择${task.title}`}/></span>}
        <span className="task-name">{task.task_kind === 'download' ? <Download size={22}/> : task.media_kind === 'audio' ? <AudioLines size={22}/> : <Video size={22}/>}<b>{task.title}</b><small>{sourceDate(task.created_at, lang)}</small></span>
        <span>{task.source_platform || (task.source_type === 'url' ? (lang === 'en' ? 'Video link' : '视频链接') : (lang === 'en' ? 'Local file' : '本地文件'))}</span>
        <span>{clock(task.duration)}</span><StatusMark task={task} lang={lang}/>
        <span>{friendlyDate(task.created_at, lang)}</span>
        <span className="task-actions">{onDelete && <button className="task-delete" aria-label={`删除${task.title}`} onClick={event => remove(event, task)}><Trash2 size={16}/></button>}<ChevronRight size={18}/></span>
      </div>)}
    </div>
  </section>
}

function Home({ tasks, refresh, onOpen, lang }) {
  const [file, setFile] = useState(null)
  const [input, setInput] = useState('')
  const [mode, setMode] = useState('transcribe')
  const [batchMode, setBatchMode] = useState(false)
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)
  const submit = async (nextFile = file, nextInput = input) => {
    setBusy(true); setError('')
    try {
      if (mode === 'transcribe' && batchMode && !nextFile) {
        const urls = nextInput.split(/\r?\n/).map(value => value.trim()).filter(Boolean)
        const result = await api.batch(urls)
        await refresh(); onOpen(result.tasks[0].id)
      } else {
        const task = mode === 'download' ? await api.download(nextInput) : nextFile ? await api.upload(nextFile) : await api.url(nextInput)
        await refresh(); onOpen(task.id)
      }
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const choose = (selected) => {
    if (!selected || busy || mode === 'download') return
    setFile(selected); setInput(''); setError('')
  }
  const clearFile = () => { setFile(null); setError('') }
  return <main className="home-page">
    <section className="home-hero">
      <div className="home-content shell">
        <div className="home-eyebrow"><span className="home-eyebrow-dot"/>{tr(lang, 'eyebrow')}</div>
        <section className="hero-copy">
          <h1>{tr(lang, 'heroOne')}<br/><span>{tr(lang, 'heroTwo')}</span></h1>
          <p>{tr(lang, 'intro')}</p>
        </section>
        <section className="home-input-panel" aria-label="创建视频听写任务">
          <div className="mode-tabs" role="tablist" aria-label="选择任务类型">
            <button type="button" role="tab" aria-selected={mode === 'transcribe'} className={mode === 'transcribe' ? 'selected' : ''} onClick={() => { setMode('transcribe'); setError('') }}><AudioLines size={18}/>{tr(lang, 'transcribe')}</button>
            <button type="button" role="tab" aria-selected={mode === 'download'} className={mode === 'download' ? 'selected' : ''} onClick={() => { setMode('download'); setFile(null); setBatchMode(false); setError('') }}><Download size={18}/>{tr(lang, 'downloadVideo')}</button>
            {mode === 'transcribe' && <button type="button" className={`batch-toggle ${batchMode ? 'selected' : ''}`} onClick={() => { setBatchMode(value => !value); setFile(null); setError('') }}>{batchMode ? '单条听写' : '批量听写'}</button>}
          </div>
          <div className={`unified-input ${drag ? 'drag' : ''} ${file ? 'has-file' : ''}`}
            onDragOver={e => { if (mode === 'transcribe') { e.preventDefault(); setDrag(true) } }} onDragLeave={() => setDrag(false)}
            onDrop={e => { e.preventDefault(); setDrag(false); if (mode === 'transcribe') choose(e.dataTransfer.files[0]); else setError('下载模式请粘贴视频链接或分享文案。') }}>
            <Link2 size={22} className="unified-input-icon" />
            {batchMode && mode === 'transcribe' ? <textarea value={input} onChange={e => { setInput(e.target.value); setFile(null) }} placeholder="每行粘贴一个视频链接，最多 20 条" aria-label="批量视频链接" rows={3}/> : <input value={file ? file.name : input} readOnly={!!file} onChange={e => { setInput(e.target.value); setFile(null) }} onKeyDown={event => {
              // Let the IME finish composing Chinese text first; a confirmed Enter
              // then follows the same path as clicking “开始听写”.
              if (event.key === 'Enter' && !event.isComposing) {
                event.preventDefault()
                if (!busy && (file || input.trim())) submit()
              }
            }} placeholder={mode === 'download' ? tr(lang, 'pasteDownload') : tr(lang, 'pasteVideo')} aria-label={lang === 'en' ? 'Video link or sharing text' : '视频链接或分享文案'} />}
            <input ref={inputRef} type="file" accept="video/*,audio/*" hidden disabled={busy || mode === 'download'} onChange={e => { choose(e.target.files[0]); e.target.value = '' }}/>
            {mode === 'transcribe' && <button type="button" className="upload-button" disabled={busy} onClick={() => inputRef.current?.click()}><Upload size={18}/>{tr(lang, 'upload')}</button>}
            <button className="home-submit" disabled={busy || (mode === 'download' ? !input.trim() : !file && !input.trim())} onClick={() => submit()}>
              {busy ? <LoaderCircle className="spin" size={19}/> : mode === 'download' ? <Download size={18}/> : <Sparkles size={18}/>}<span>{busy ? mode === 'download' ? tr(lang, 'parsing') : tr(lang, 'submitting') : mode === 'download' ? tr(lang, 'startDownload') : tr(lang, 'start')}</span>
            </button>
          </div>
          {file && <span className="file-pill">{file.type.startsWith('audio/') ? <AudioLines size={15}/> : <Video size={15}/>} {file.name} · {fileSize(file.size)}<button type="button" aria-label="移除已选文件" title="移除文件" onClick={clearFile}><X size={15}/></button></span>}
          <div className="home-form-foot">
            <p className="unified-hint">{mode === 'download' ? tr(lang, 'hintDownload') : file ? tr(lang, 'hintFile') : tr(lang, 'hintTranscribe')}</p>
            {error && <div className="error-line spacious">{error}</div>}
          </div>
        </section>
        <div className="home-platforms"><span>{tr(lang, 'platforms')}</span><i/>抖音<i/>小红书<i/>B 站<i/>YouTube<i/>{tr(lang, 'localMedia')}</div>
        <div className="home-benefits"><span><Check size={16}/>{tr(lang, 'benefit1')}</span><span><LockKeyhole size={15}/>{tr(lang, 'benefit2')}</span><span><Clock3 size={15}/>{tr(lang, 'benefit3')}</span></div>
      </div>
    </section>
    <section className="home-followup">
      <section className="home-recent shell"><TaskTable tasks={tasks.slice(0, 5)} onOpen={onOpen} lang={lang}/></section>
      <section className="home-learn shell">
        <div className="learn-heading"><span>{tr(lang, 'learnEyebrow')}</span><h2>{tr(lang, 'learnTitle')}</h2><p>{tr(lang, 'learnIntro')}</p></div>
        <div className="learn-grid">
          <article className="learn-card"><span className="learn-icon"><AudioLines size={21}/></span><h3>{tr(lang, 'feature1Title')}</h3><p>{tr(lang, 'feature1')}</p><small>01</small></article>
          <article className="learn-card"><span className="learn-icon"><Download size={21}/></span><h3>{tr(lang, 'feature2Title')}</h3><p>{tr(lang, 'feature2')}</p><small>02</small></article>
          <article className="learn-card"><span className="learn-icon"><WandSparkles size={21}/></span><h3>{tr(lang, 'feature3Title')}</h3><p>{tr(lang, 'feature3')}</p><small>03</small></article>
        </div>
        <div className="learn-flow"><span><i>1</i>{tr(lang, 'step1')}</span><b/><span><i>2</i>{tr(lang, 'step2')}</span><b/><span><i>3</i>{tr(lang, 'step3')}</span></div>
        <p className="learn-footer">{tr(lang, 'pageEnd')}</p>
      </section>
    </section>
  </main>
}

function TranscriptEditor({ segments, showTimes, showSpeakers, onChange }) {
  const areaRef = useRef(null)
  const value = segments.map(segment => {
    const speaker = showSpeakers && segment.speaker ? `[${segment.speaker}] ` : ''
    return `${showTimes ? `[${segment.start}] ` : ''}${speaker}${segment.text}`
  }).join('\n')
  useEffect(() => {
    const area = areaRef.current
    if (!area) return
    area.style.height = 'auto'
    area.style.height = `${Math.min(560, Math.max(260, area.scrollHeight))}px`
    area.style.overflowY = area.scrollHeight > 560 ? 'auto' : 'hidden'
  }, [value])
  const edit = event => {
    const lines = event.target.value.split(/\r?\n/)
    onChange(lines.map((line, index) => {
      const base = segments[index] || { start: '', end: '', start_seconds: 0, end_seconds: 0 }
      let text = showTimes ? line.replace(/^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*/, '') : line
      if (base.speaker) {
        const escapedSpeaker = base.speaker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
        text = text.replace(new RegExp(`^\\s*\\[${escapedSpeaker}\\]\\s*`), '')
      }
      return {...base, text}
    }))
  }
  return <div className="transcript-editor"><textarea ref={areaRef} value={value} onChange={edit} spellCheck="false" wrap="soft" placeholder="听写内容会显示在这里…" /></div>
}

function clockSeconds(value) {
  const parts = String(value || '').trim().split(':').map(Number)
  if (parts.some(Number.isNaN)) return null
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts.length === 1 ? parts[0] : null
}

function HighlightResults({ items, onSeek }) {
  return <div className="ai-results"><div className="result-heading"><Sparkles size={18}/><b>找到 {items.length} 个亮点</b></div>
    {items.map((item, index) => <article className="highlight" key={index}>
      <div><span className="score">{item.score || 8}</span><b>{item.title || `亮点 ${index + 1}`}</b><button className="time-link" onClick={() => onSeek?.(item.start)}>{item.start}–{item.end}</button></div>
      <blockquote>{item.original_text}</blockquote><p>{item.reason}</p>
    </article>)}
  </div>
}

function VisualResults({ items, onSeek }) {
  const style = items.find(item => item.kind === 'style_analysis')
  const scenes = items.filter(item => item.kind !== 'style_analysis')
  return <div className="visual-results"><div className="result-heading"><Film size={18}/><b>画面分析</b><small>{scenes.length} 个关键画面</small></div>
    {style && <article className="visual-style-card"><div className="visual-style-title"><Sparkles size={17}/><b>整体画面风格</b></div><div className="visual-style-grid">
      {[["整体调性", style.overall_style], ["色彩与光线", style.color_lighting], ["构图与镜头", style.composition_camera], ["剪辑节奏", style.editing_rhythm], ["字幕与包装", style.text_graphics]].filter(([, value]) => value).map(([label, value]) => <div key={label}><small>{label}</small><p>{value}</p></div>)}
    </div>{style.replication_tips && <div className="visual-replication-tips"><b>复刻建议</b><p>{style.replication_tips}</p></div>}</article>}
    {scenes.map((item, index) => <article className="visual-item" key={index}>
      <div><button className="time-link" onClick={() => onSeek?.(item.timestamp)}>{item.timestamp || `画面 ${index + 1}`}</button><span>{item.suggested_use || '视觉信息'}</span></div>
      <p>{item.description || '未提供画面描述'}</p>
      {item.onscreen_text && <small>画面文字：{item.onscreen_text}</small>}
      {item.visual_hook && <small>亮点：{item.visual_hook}</small>}
    </article>)}
  </div>
}

function inlineMarkdown(value, keyPrefix) {
  const parts = String(value || '').split(/(\*\*[^*]+\*\*|`[^`]+`)/g)
  return parts.map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) return <strong key={`${keyPrefix}-b-${index}`}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`')) return <code key={`${keyPrefix}-c-${index}`}>{part.slice(1, -1)}</code>
    return <span key={`${keyPrefix}-t-${index}`}>{part}</span>
  })
}

function MarkdownPreview({ value }) {
  const lines = String(value || '').replace(/^```(?:markdown)?\s*/i, '').replace(/\s*```$/i, '').split(/\r?\n/)
  const blocks = []
  let list = null
  const flushList = () => {
    if (!list) return
    const Tag = list.type === 'ol' ? 'ol' : 'ul'
    blocks.push(<Tag key={`list-${blocks.length}`}>{list.items.map((item, index) => <li key={index}>{inlineMarkdown(item, `li-${index}`)}</li>)}</Tag>)
    list = null
  }
  lines.forEach((line, index) => {
    const trimmed = line.trim()
    if (!trimmed) { flushList(); return }
    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) { flushList(); const Tag = `h${Math.min(6, heading[1].length)}`; blocks.push(<Tag key={`heading-${index}`}>{inlineMarkdown(heading[2], `h-${index}`)}</Tag>); return }
    const unordered = trimmed.match(/^[-*]\s+(.+)$/)
    const ordered = trimmed.match(/^\d+[.)]\s+(.+)$/)
    if (unordered || ordered) {
      const type = ordered ? 'ol' : 'ul'
      if (!list || list.type !== type) { flushList(); list = {type, items: []} }
      list.items.push((unordered || ordered)[1]); return
    }
    flushList(); blocks.push(<p key={`paragraph-${index}`}>{inlineMarkdown(trimmed, `p-${index}`)}</p>)
  })
  flushList()
  return <div className="markdown-preview">{blocks.length ? blocks : <p className="empty-markdown">暂无改编内容</p>}</div>
}

function SourceMedia({ task, displayProgress, mediaRef, mediaSrc, mediaMode, mediaRetryCount, onMediaError, onRetryMedia, onCopyLink, onDownloadVideo, downloadBusy }) {
  const [videoRatio, setVideoRatio] = useState(16 / 9)
  const playbackAudioRef = useRef(null)
  const remoteVideo = mediaMode === 'remote' && Boolean(task.playback_url) && task.playback_kind === 'video'
  const linkedVideo = task.source_type === 'url' && !/\.(mp3|wav|m4a|aac|flac|ogg|opus)(?:$|[?#])/i.test(task.source_url || '')
  const localPlaybackKind = task.local_playback_kind || task.local_media_kind
  const isVideo = remoteVideo || mediaMode === 'preparing' || (mediaMode === 'local' ? localPlaybackKind === 'video' : linkedVideo || task.media_kind === 'video')
  const coverUrl = `/api/tasks/${task.id}/cover`
  const audioUrl = `/api/tasks/${task.id}/audio`
  const playbackAudioSrc = `/api/tasks/${task.id}/playback-audio?v=${mediaRetryCount}`
  const syncPlaybackAudio = () => {
    const video = mediaRef.current
    const audio = playbackAudioRef.current
    if (!video || !audio || audio.readyState < 1 || Math.abs(audio.currentTime - video.currentTime) < 0.45) return
    try { audio.currentTime = video.currentTime } catch {}
  }
  const startPlaybackAudio = () => {
    const audio = playbackAudioRef.current
    if (!audio) return
    syncPlaybackAudio()
    audio.play().catch(() => {})
  }
  const stopPlaybackAudio = () => playbackAudioRef.current?.pause()
  return <section className="media-column-card">
      <div className="media-section-heading"><h2>{isVideo ? '视频' : '音频'}</h2>{isVideo && <span>{clock(task.duration)}</span>}</div>
      {isVideo && <div className={`source-preview ${videoRatio < 1 ? 'portrait' : ''}`}>
        {task.source_available && mediaMode !== 'failed'
          ? mediaMode === 'preparing'
            ? <div className="source-pending"><LoaderCircle className="spin" size={25}/><b>正在准备视频…</b></div>
            : <><video key={`${mediaSrc}-${mediaRetryCount}`} ref={mediaRef} className="source-video" style={{'--video-ratio': videoRatio}} controls muted={remoteVideo && task.playback_audio_available} poster={task.cover_available ? coverUrl : undefined} src={mediaSrc} onPlay={startPlaybackAudio} onPause={stopPlaybackAudio} onSeeking={syncPlaybackAudio} onTimeUpdate={syncPlaybackAudio} onEnded={stopPlaybackAudio} onLoadedMetadata={event => {
            const {videoWidth, videoHeight} = event.currentTarget
            if (videoWidth > 0 && videoHeight > 0) setVideoRatio(videoWidth / videoHeight)
          }} onError={onMediaError}/>{remoteVideo && task.playback_audio_available && <audio key={playbackAudioSrc} ref={playbackAudioRef} src={playbackAudioSrc} onLoadedMetadata={syncPlaybackAudio} onError={() => { if (mediaRef.current) mediaRef.current.muted = false }} style={{display: 'none'}}/>}</>
          : <div className="source-pending">{['completed','failed'].includes(task.status) || mediaMode === 'failed' ? null : <LoaderCircle className="spin" size={25}/>}<b>{mediaMode === 'failed' || task.status === 'failed' ? '原视频暂不可用' : task.status === 'completed' ? '原视频已清理' : '正在解析视频素材'}</b><span>{mediaMode === 'failed' && task.source_available ? '视频暂时无法播放。' : task.status === 'completed' && !task.source_available ? '听写稿仍然保留。' : task.message}{!['completed','failed'].includes(task.status) ? ` · ${displayProgress}%` : ''}</span>{mediaMode === 'failed' && task.source_available && <button type="button" className="outline compact" onClick={onRetryMedia}>重试播放</button>}</div>}
      </div>}
      <div className="source-actions">
        {isVideo && task.cover_available && <a className="outline compact" href={coverUrl} download><Download size={16}/>保存封面</a>}
        {task.source_url && <button className="outline compact" onClick={onCopyLink}><Copy size={16}/>复制链接</button>}
        {task.source_url && <button className="primary compact" disabled={downloadBusy} onClick={onDownloadVideo}>{downloadBusy ? <LoaderCircle className="spin" size={16}/> : <Download size={16}/>}下载视频</button>}
      </div>
      <div className="media-divider"/>
      <section className="asset-section">
        <div className="media-section-heading"><h3>音频</h3>{task.audio_available && <a className="audio-download" href={audioUrl} download><Download size={16}/>下载音频</a>}</div>
        {task.audio_available
          ? <audio className="asset-audio-player" controls preload="metadata" src={audioUrl}/>
          : <div className="audio-pending">{['completed','failed'].includes(task.status) ? null : <LoaderCircle className="spin" size={16}/>} {task.status === 'failed' || task.status === 'completed' ? '音频暂不可用' : '正在准备音频…'}</div>}
      </section>
      {isVideo && <section className="asset-section image-list-section">
        <div className="media-section-heading"><h3>图片列表</h3></div>
        {task.cover_available
          ? <a className="cover-tile" href={coverUrl} download aria-label="下载视频封面"><img src={coverUrl} alt="视频封面"/><span><Download size={20}/>下载封面</span></a>
          : <div className="cover-pending">{task.status === 'failed' || task.status === 'completed' ? '封面暂不可用' : '正在生成封面…'}</div>}
      </section>}
      <small className="media-retention-note">视频和音频会在 24 小时后自动清理，听写稿会保留。</small>
    </section>
}

function Detail({ taskId, onBack, refresh, onOpen }) {
  const [task, setTask] = useState(null)
  const displayProgress = Math.round(useTaskDisplayProgress(task))
  const [segments, setSegments] = useState([])
  const [search, setSearch] = useState('')
  const showTimes = false
  const showSpeakers = false
  const [dirty, setDirty] = useState(false)
  const [direction, setDirection] = useState('')
  const [action, setAction] = useState(null)
  const [rewriteView, setRewriteView] = useState('preview')
  const [translateLanguage, setTranslateLanguage] = useState('英语')
  const [activeTool, setActiveTool] = useState('highlights')
  const [notice, setNotice] = useState('')
  const [retryBusy, setRetryBusy] = useState(false)
  const [mediaMode, setMediaMode] = useState('remote')
  const [downloadBusy, setDownloadBusy] = useState(false)
  const [mediaRetryCount, setMediaRetryCount] = useState(0)
  const [mediaRefreshAttempted, setMediaRefreshAttempted] = useState(false)
  const mediaRef = useRef(null)
  const playbackFallbackInProgress = useRef(false)
  const taskIdRef = useRef(taskId)
  const dirtyRef = useRef(dirty)
  const loadRequestRef = useRef(0)
  taskIdRef.current = taskId
  dirtyRef.current = dirty
  const load = useCallback(async () => {
    const requestId = ++loadRequestRef.current
    const next = await api.task(taskId)
    // A slower response from an earlier poll must not replace newer task data.
    if (requestId !== loadRequestRef.current || taskIdRef.current !== taskId) return next
    setTask(next)
    if (!dirtyRef.current) setSegments(next.segments || [])
    return next
  }, [taskId])
  const retryFailedTask = async () => {
    setRetryBusy(true); setNotice('')
    try {
      await api.retryTask(taskId)
      await Promise.all([load(), refresh()])
    } catch (err) { setNotice(err.message) }
    finally { setRetryBusy(false) }
  }
  useEffect(() => { load().catch(console.error) }, [load])
  useEffect(() => { setMediaMode('remote'); setMediaRetryCount(0); setMediaRefreshAttempted(false); playbackFallbackInProgress.current = false }, [taskId])
  const visualTaskRunning = task && !['idle', 'completed', 'failed'].includes(task.visual_status || 'idle')
  const aiTaskRunning = task && !['idle', 'completed', 'failed'].includes(task.ai_status)
  const shouldPoll = Boolean(task && task.status !== 'failed' && (task.status !== 'completed' || aiTaskRunning || visualTaskRunning))
  useEffect(() => {
    if (!shouldPoll) return
    let timer
    let cancelled = false
    const poll = async () => {
      try { await load() } catch (err) { console.error(err) }
      if (!cancelled) timer = setTimeout(poll, 1800)
    }
    timer = setTimeout(poll, 1800)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [shouldPoll, load])
  const save = async () => { setTask(await api.saveTranscript(taskId, segments)); setDirty(false); setNotice('已保存修改') }
  const showHighlights = () => { setActiveTool('highlights'); setAction(null); setNotice('') }
  const startHighlights = async () => {
    showHighlights(); setAction('highlights')
    try { await api.highlights(taskId); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const startSummary = async () => {
    setActiveTool('summary'); setAction('summary'); setNotice('')
    try { await api.summarize(taskId); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const startTranslation = async () => {
    setActiveTool('translate'); setAction('translate'); setNotice('')
    try { await api.translate(taskId, translateLanguage); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const showVisualAnalysis = () => { setActiveTool('visual'); setAction(null); setNotice('') }
  const startVisualAnalysis = async () => {
    showVisualAnalysis(); setAction('visual')
    try { await api.visualAnalysis(taskId); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const startRewrite = async () => {
    setActiveTool('rewrite'); setAction('rewrite'); setNotice('')
    try { await api.rewrite(taskId, direction); await load() }
    catch (err) { setAction('rewrite'); setNotice(err.message) }
  }
  const copySourceLink = async () => {
    try { await navigator.clipboard.writeText(task.source_url); setNotice('已复制原视频链接') }
    catch { setNotice('复制失败，请检查浏览器剪贴板权限') }
  }
  const copyResultText = async (value, label) => {
    try { await navigator.clipboard.writeText(value); setNotice(`已复制${label}`) }
    catch { setNotice('复制失败，请检查浏览器剪贴板权限') }
  }
  const downloadOriginalVideo = async () => {
    if (!task.source_url || downloadBusy) return
    setDownloadBusy(true); setNotice('')
    try {
      const downloadTask = await api.download(task.source_url)
      await refresh()
      onOpen(downloadTask.id)
    } catch (err) { setNotice(err.message) }
    finally { setDownloadBusy(false) }
  }
  const seekTo = useCallback((value) => {
    const seconds = clockSeconds(value)
    if (seconds === null || !mediaRef.current) return
    mediaRef.current.currentTime = seconds
    mediaRef.current.play().catch(() => {})
  }, [])
  const mediaSrc = `/api/tasks/${taskId}/media?${mediaMode === 'local' ? 'local=1&' : ''}v=${mediaRetryCount}`
  const linkedVideo = task?.source_type === 'url' && !/\.(mp3|wav|m4a|aac|flac|ogg|opus)(?:$|[?#])/i.test(task?.source_url || '')
  const preparePlaybackFallback = async () => {
    if (playbackFallbackInProgress.current) return
    playbackFallbackInProgress.current = true
    setNotice('')
    setMediaMode('preparing')
    try {
      await api.preparePlaybackVideo(taskId)
      await load()
      setMediaMode('local')
      setMediaRetryCount(current => current + 1)
    } catch {
      setMediaMode('failed')
      setNotice('视频暂时无法播放，请稍后重试。')
    } finally {
      playbackFallbackInProgress.current = false
    }
  }
  useEffect(() => {
    if (!task || mediaMode !== 'remote' || !linkedVideo || !task.source_available) return
    if (task.playback_fallback_available) {
      setMediaMode('local')
      setMediaRetryCount(current => current + 1)
      return
    }
    if (!task.playback_url || task.playback_kind !== 'video') void preparePlaybackFallback()
  }, [task?.id, task?.playback_url, task?.playback_kind, task?.playback_fallback_available, mediaMode, linkedVideo])
  const handleMediaError = async () => {
    if (playbackFallbackInProgress.current) return
    if (mediaMode === 'remote' && task?.source_platform === '抖音' && !mediaRefreshAttempted) {
      setMediaRefreshAttempted(true)
      try {
        await api.refreshPlayback(taskId)
        await load()
        setMediaRetryCount(current => current + 1)
        return
      } catch {}
    }
    if (mediaMode === 'remote' && linkedVideo) {
      await preparePlaybackFallback()
      return
    }
    setNotice('视频暂时无法播放，请稍后重试。')
    setMediaMode('failed')
  }
  const retryMedia = () => {
    setMediaMode('remote')
    setMediaRefreshAttempted(false)
    setMediaRetryCount(current => current + 1)
  }
  if (!task) return <main className="loading-page"><LoaderCircle className="spin"/>加载中</main>
  if (task.task_kind === 'download') {
    if (task.status === 'completed') return <DownloadReady task={task} onBack={onBack}/>
    if (task.status === 'failed') return <main className="processing shell"><button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button><div className="processing-center"><span className="process-icon failed"><RotateCcw/></span><h1>视频下载失败</h1><p>{task.error || task.message}</p>{notice && <div className="error-line">{notice}</div>}<button className="primary compact" disabled={retryBusy} onClick={retryFailedTask}>{retryBusy ? <LoaderCircle className="spin" size={17}/> : <RotateCcw size={17}/>}重新提交下载</button></div></main>
    return <main className="processing shell"><button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button><div className="processing-center"><span className="process-icon"><LoaderCircle className="spin"/></span><h1>{task.message || '正在下载视频'}</h1><p>{task.title}</p><div className="big-progress"><i style={{width: `${displayProgress}%`}}/></div><b>{displayProgress}%</b></div></main>
  }
  const visible = segments.map((item, index) => ({...item, _index: index}))
    .filter(item => !search || item.text.toLowerCase().includes(search.toLowerCase()))
  const updateVisible = next => {
    const indexes = visible.map(item => item._index)
    setSegments(current => current.map((item, index) => {
      const visibleIndex = indexes.indexOf(index)
      return visibleIndex >= 0 && next[visibleIndex] ? {...item, text: next[visibleIndex].text} : item
    }))
    setDirty(true)
  }
  const visualRunning = !['idle', 'completed', 'failed'].includes(task.visual_status || 'idle')
  const running = !['idle', 'completed', 'failed'].includes(task.ai_status) || visualRunning
  const hasVisualStyle = task.visual_analysis?.some(item => item.kind === 'style_analysis')
  const canAnalyzeVisuals = task.media_kind !== 'audio' || (Boolean(task.playback_url) && task.playback_kind === 'video')
  const transcriptionComplete = task.status === 'completed' && displayProgress >= 100
  const transcriptionFailed = task.status === 'failed'
  const transcriptPreview = segments.slice(0, 2).map(segment => segment.text).join(' ')
  return <main className="detail shell">
    <div className="detail-head"><button type="button" className="detail-back-button" onClick={onBack} aria-label="返回工作台" title="返回工作台"><ArrowLeft size={21}/></button><h1>文案提取结果</h1></div>
    <section className="result-overview">
      <div className="result-meta"><span className="result-chip platform-chip">{task.source_platform || '本地文件'}</span><span className={`result-chip ${transcriptionComplete ? 'complete-chip' : transcriptionFailed ? 'failed-chip' : 'working-chip'}`}>{transcriptionComplete ? '提取结果：原文' : transcriptionFailed ? '提取失败' : '正在提取文案'}</span><span className="result-duration">时长：{clock(task.duration)}</span>{task.source_url && <a className="original-link" href={task.source_url} target="_blank" rel="noreferrer"><ExternalLink size={16}/>访问原文</a>}</div>
      <div className="result-title-row"><h2>{task.title || '暂无标题'}</h2><button type="button" className="icon-button" aria-label="复制视频标题" title="复制视频标题" onClick={() => copyResultText(task.title || '', '视频标题')}><Copy size={17}/></button></div>
      <div className="result-excerpt-row"><p>{transcriptPreview || (transcriptionFailed ? task.error : transcriptionComplete ? '暂无听写内容' : `${task.message} ${displayProgress}%`)}</p>{transcriptPreview && <button type="button" className="icon-button" aria-label="复制文案摘要" title="复制文案摘要" onClick={() => copyResultText(transcriptPreview, '文案摘要')}><Copy size={17}/></button>}</div>
    </section>
    {notice && <div className="notice inline-notice">{notice}</div>}
    <div className={`detail-result-grid ${transcriptionComplete ? '' : 'pending-grid'}`}>
      <SourceMedia task={task} displayProgress={displayProgress} mediaRef={mediaRef} mediaSrc={mediaSrc} mediaMode={mediaMode} mediaRetryCount={mediaRetryCount} onMediaError={handleMediaError} onRetryMedia={retryMedia} onCopyLink={copySourceLink} onDownloadVideo={downloadOriginalVideo} downloadBusy={downloadBusy}/>
      <section className="transcript-column-card">
        {transcriptionComplete ? <>
          <div className="ai-panel">
            <span className="ai-panel-label"><Sparkles size={16}/>用 AI 做更多</span>
            <p>将视频文案作为输入，选择一个工具继续处理。</p>
            <div className="ai-tool-buttons">
              <button className={`ai-tool-button summary-tool ${activeTool === 'summary' ? 'active' : ''}`} disabled={running} onClick={task.summary_text ? () => { setActiveTool('summary'); setAction(null) } : startSummary}><Sparkles size={17}/>{task.ai_status === 'summarizing' ? '总结中…' : task.summary_text ? '查看摘要' : 'AI 总结'}</button>
              <button className={`ai-tool-button highlights-tool ${activeTool === 'highlights' ? 'active' : ''}`} disabled={running} onClick={task.highlights?.length ? showHighlights : startHighlights}><WandSparkles size={17}/>{task.ai_status === 'highlighting' ? '提取中…' : task.highlights?.length ? '精彩片段' : '提取精彩片段'}</button>
              <button className={`ai-tool-button visual-tool ${activeTool === 'visual' ? 'active' : ''}`} disabled={running || !canAnalyzeVisuals || !task.source_available || ['queued','analyzing'].includes(task.visual_status)} onClick={task.visual_analysis?.length && hasVisualStyle ? showVisualAnalysis : startVisualAnalysis}><Film size={17}/>{['queued','analyzing'].includes(task.visual_status) ? '分析中…' : task.visual_analysis?.length ? '查看画面分析' : '分析画面'}</button>
              <button className={`ai-tool-button rewrite-tool ${activeTool === 'rewrite' ? 'active' : ''}`} disabled={running} onClick={() => { setActiveTool('rewrite'); setAction(task.rewrite_text ? null : 'rewrite'); setNotice('') }}><PencilLine size={17}/>{task.rewrite_text ? '查看改写稿' : '改写文案'}</button>
              <button className={`ai-tool-button translate-tool ${activeTool === 'translate' ? 'active' : ''}`} disabled={running} onClick={() => { setActiveTool('translate'); setAction(task.translated_text ? null : 'translate'); setNotice('') }}><Languages size={17}/>{task.translated_text ? '查看译文' : '翻译文案'}</button>
            </div>
          </div>
          {action === 'rewrite' && <div className="rewrite-form"><label><span>新稿方向</span><small>可以调整方向后再次生成</small><textarea value={direction} onChange={e => setDirection(e.target.value)} placeholder="例如：改成面向新手的 60 秒口播，语气自然、有反差感"/></label><button className="primary compact" disabled={running} onClick={startRewrite}>生成新文案</button></div>}
          {action === 'translate' && <div className="rewrite-form translation-form"><label><span>翻译目标语言</span><select value={translateLanguage} onChange={event => setTranslateLanguage(event.target.value)}><option>英语</option><option>简体中文</option><option>繁體中文</option><option>日语</option><option>韩语</option><option>西班牙语</option><option>法语</option></select></label><button className="primary compact" disabled={running} onClick={startTranslation}>开始翻译</button></div>}
          <div className="transcript-section-heading"><div><h2>视频文案</h2><span>{segments.length} 段听写</span></div></div>
          <div className="transcript-tools"><label><Search size={18}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索文案" /></label>
            <button className="outline compact" onClick={() => copyResultText((search ? visible : segments).map(x => x.text).join('\n'), search ? '搜索结果' : '完整文案')}><Copy size={17}/>{search ? `复制搜索结果 (${visible.length})` : '复制文案'}</button>
            <a className="outline compact" href={`/api/tasks/${task.id}/export/txt`}><Download size={17}/>TXT</a>
            <a className="outline compact" href={`/api/tasks/${task.id}/export/srt`}><Download size={17}/>SRT</a>
            {dirty && <button className="primary compact" onClick={save}>保存修改</button>}
          </div>
          <TranscriptEditor segments={visible} showTimes={showTimes} showSpeakers={showSpeakers} onChange={updateVisible}/>
          <div className="next-results">
            {running && <div className="ai-running"><LoaderCircle className="spin" size={18}/>{task.ai_message}</div>}
            {task.ai_status === 'failed' && <div className="error-line">{task.ai_message}</div>}
            {activeTool === 'highlights' && (task.highlights?.length > 0 ? <HighlightResults items={task.highlights} onSeek={seekTo}/> : <div className="result-empty">提取的精彩片段会显示在这里。</div>)}
            {activeTool === 'summary' && (task.summary_text ? <div className="rewrite-result"><div className="result-heading"><Sparkles size={18}/><b>AI 文案摘要</b><button onClick={() => copyResultText(task.summary_text, 'AI 摘要')}><Copy size={16}/>复制</button></div><div className="rewrite-output"><MarkdownPreview value={task.summary_text}/></div></div> : <div className="result-empty">生成的摘要会显示在这里。</div>)}
            {activeTool === 'visual' && (task.visual_analysis?.length > 0 ? <VisualResults items={task.visual_analysis} onSeek={seekTo}/> : <div className="result-empty">视频画面分析结果会显示在这里。</div>)}
            {activeTool === 'rewrite' && (task.rewrite_text ? <div className="rewrite-result"><div className="result-heading"><PencilLine size={18}/><b>新口播稿</b><div className="result-switch"><button className={rewriteView === 'preview' ? 'active' : ''} onClick={() => setRewriteView('preview')}>预览</button><button className={rewriteView === 'edit' ? 'active' : ''} onClick={() => setRewriteView('edit')}>编辑</button></div><button onClick={() => copyResultText(task.rewrite_text, '改写稿')}><Copy size={16}/>复制</button></div><div className="rewrite-output">{rewriteView === 'edit' ? <textarea value={task.rewrite_text} onChange={event => setTask(current => ({...current, rewrite_text: event.target.value}))} spellCheck="false" /> : <MarkdownPreview value={task.rewrite_text}/>}</div></div> : <div className="result-empty">生成的新口播稿会显示在这里。</div>)}
            {activeTool === 'translate' && (task.translated_text ? <div className="rewrite-result"><div className="result-heading"><Languages size={18}/><b>{task.translation_language || '翻译结果'}</b><button onClick={() => copyResultText(task.translated_text, '翻译稿')}><Copy size={16}/>复制</button></div><div className="rewrite-output"><MarkdownPreview value={task.translated_text}/></div></div> : <div className="result-empty">选择目标语言后开始翻译，译文会显示在这里。</div>)}
            <div className="retention"><span>视频和音频会在 24 小时后自动清理，听写稿会保留。</span>{task.source_available && <button onClick={async () => { if(confirm('立即删除原视频？听写稿会保留。')) { await api.deleteSource(task.id); load() } }}><Trash2 size={16}/>立即删除素材</button>}</div>
          </div>
        </> : <div className={`transcript-pending ${transcriptionFailed ? 'failed' : ''}`}>
          {transcriptionFailed ? <RotateCcw size={25}/> : <span className="pending-wave"><i/><i/><i/><i/><i/></span>}
          <div><h2>{transcriptionFailed ? '文案提取失败' : task.status === 'completed' ? '正在整理听写结果' : 'AI 正在提取视频文案'}</h2><p>{transcriptionFailed ? task.error : task.status === 'completed' ? '听写已完成，正在整理结果…' : `${task.message}，完成后会显示在这里。`}</p></div>
          {!transcriptionFailed && <div className="big-progress"><i style={{width: `${displayProgress}%`}}/></div>}
          {!transcriptionFailed && <b>{displayProgress}%</b>}
          {transcriptionFailed && <div className="retry-task-actions"><button className="primary compact" disabled={retryBusy} onClick={retryFailedTask}>{retryBusy ? <LoaderCircle className="spin" size={17}/> : <RotateCcw size={17}/>}重新提交听写</button></div>}
        </div>}
      </section>
    </div>
  </main>
}

function DownloadReady({ task, onBack }) {
  return <main className="download-ready shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button>
    <section className="download-card">
      <span className="process-icon"><Check/></span>
      <h1>{task.source_available ? '视频已准备好' : '下载文件已过期'}</h1>
      <h2>{task.title}</h2>
      <p>{task.source_platform || '网络视频'} · {sourceDate(task.created_at)}</p>
      {task.source_available ? <><a className="primary" href={`/api/tasks/${task.id}/download`}><Download size={19}/>保存视频到电脑</a><small>文件会在 24 小时后从服务器自动清理；你下载到电脑的副本不受影响。</small></> : <p className="expired-note">服务器临时文件已自动清理。请回到首页重新提交链接。</p>}
    </section>
  </main>
}

function MembershipPage({ lang, onBack }) {
  const [billing, setBilling] = useState(null)
  const [plans, setPlans] = useState([])
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState('')
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [tier, setTier] = useState('standard')
  const en = lang === 'en'
  const load = useCallback(async () => {
    const [current, choices, requests] = await Promise.all([api.billing(), api.plans(), api.billingOrders()])
    setBilling(current); setPlans(choices); setOrders(requests)
  }, [])
  useEffect(() => { load().catch(err => setError(err.message)).finally(() => setLoading(false)) }, [load])
  const apply = async plan => {
    setBusy(plan.code); setMessage(''); setError('')
    try {
      await api.requestPlan(plan.code)
      await load()
      setMessage(en ? 'Request submitted. An administrator will confirm payment and activate the plan.' : '申请已提交。管理员确认收款后会为你开通套餐。')
    } catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const cancelRequest = async order => {
    setBusy(order.plan_code); setMessage(''); setError('')
    try { await api.cancelBillingOrder(order.id); await load(); setMessage(en ? 'Request cancelled.' : '已撤回开通申请。') }
    catch (err) { setError(err.message) } finally { setBusy('') }
  }
  const currentCode = billing?.plan?.code
  const activeRequest = orders.find(order => order.status === 'requested')
  const activePlanName = plan => en ? ({free:'Free trial',pro_monthly:'PRO Monthly',pro_yearly:'PRO Yearly',pro_lifetime:'PRO Lifetime',ultra_monthly:'Ultra Monthly',ultra_quarterly:'Ultra Quarterly',ultra_yearly:'Ultra Yearly'}[plan?.code] || plan?.name) : plan?.name
  const termLabel = plan => plan.term_days === 0 ? (en ? 'Lifetime access' : '永久有效') : plan.term_days === 30 ? (en ? '30 days' : '月卡 · 30天') : plan.term_days === 90 ? (en ? '90 days' : '季卡 · 90天') : plan.term_days === 365 ? (en ? '1 year' : '年卡 · 365天') : `${plan.term_days} ${en ? 'days' : '天'}`
  const quotaLabel = plan => `${plan.monthly_minutes >= 60 ? `${plan.monthly_minutes / 60}${en ? ' hr' : ' 小时'}` : `${plan.monthly_minutes} ${en ? 'min' : '分钟'}`}${en ? ' transcription / month' : '听写时长/月'}`
  const aiQuota = (plan, feature) => { const value = plan.ai_limits?.[feature] ?? 0; return value < 0 ? (en ? 'Unlimited' : '不限次') : `${value}${en ? ' / month' : ' 次/月'}` }
  const tierPlans = plans.filter(plan => plan.tier === tier && plan.code !== 'free')
  return <main className="membership-page shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>{en ? 'Back to workspace' : '返回工作台'}</button>
    <section className="membership-hero">
      <span className="membership-eyebrow"><Crown size={15}/>{en ? 'MEMBERSHIP' : '听见会员'}</span>
      <h1>{en ? 'A clearer workflow for every video.' : '让视频文案整理，更顺手一点'}</h1>
      <p>{en ? 'Transcribe, review, and turn video into reusable content in one private workspace.' : '从视频听写到后续创作，在一个私密工作台里完成。根据你的使用量选择合适的会员方案。'}</p>
    </section>
    <section className="membership-intro">
      <h2>{en ? 'Everything you need to work with video content' : '会员方案，覆盖视频内容整理常用流程'}</h2>
      <div className="membership-feature-grid">
        <article><span><AudioLines size={19}/></span><div><b>{en ? 'Video transcription' : '视频转文字'}</b><p>{en ? 'Extract editable transcripts from supported video links and local media.' : '从支持的平台链接或本地素材提取可编辑文案。'}</p></div></article>
        <article><span><Layers3 size={19}/></span><div><b>{en ? 'Concurrent tasks' : '并发处理'}</b><p>{en ? 'Higher plans let you process more tasks at the same time.' : '按套餐并发处理多个任务，减少等待。'}</p></div></article>
        <article><span><Download size={19}/></span><div><b>{en ? 'Collect media assets' : '整理视频素材'}</b><p>{en ? 'Save source video, audio, and cover images for your workflow.' : '按需保存原视频、音频和封面，素材整理更方便。'}</p></div></article>
        <article><span><WandSparkles size={19}/></span><div><b>{en ? 'Continue creating' : '继续分析与创作'}</b><p>{en ? 'Find highlights, analyze visuals, or rewrite a script when you choose.' : '听写后可主动找亮点、分析画面或改写脚本。'}</p></div></article>
      </div>
    </section>
    {billing && <section className="membership-current">
      <div><small>{en ? 'CURRENT PLAN' : '当前套餐'}</small><h2>{activePlanName(billing.plan)}</h2><p>{billing.unlimited ? (en ? 'Unlimited transcription' : '听写额度不限量') : `${billing.remaining_minutes} ${en ? 'min remaining this cycle' : '分钟剩余'}`}</p></div>
      <div className="membership-meter"><span style={{width: `${billing.unlimited ? 100 : Math.min(100, billing.used_minutes / Math.max(1,billing.plan.monthly_minutes) * 100)}%`}}/></div>
      <small>{billing.unlimited ? (en ? 'Unlimited' : '不限量') : `${billing.used_minutes} / ${billing.plan.monthly_minutes} ${en ? 'min used' : '分钟已用'}`}{billing.expires_at && ` · ${en ? 'Expires' : '到期'} ${new Date(billing.expires_at).toLocaleDateString(en ? 'en-US' : 'zh-CN')}`}</small>
    </section>}
    {activeRequest && <div className="membership-pending"><Clock3 size={17}/><span>{en ? `Pending request: ${activePlanName(plans.find(plan => plan.code === activeRequest.plan_code)) || activeRequest.plan_code}. Payment has not been confirmed.` : `待处理申请：${activePlanName(plans.find(plan => plan.code === activeRequest.plan_code)) || activeRequest.plan_code}。当前尚未确认收款。`}</span><button type="button" disabled={busy !== ''} onClick={() => cancelRequest(activeRequest)}>{en ? 'Cancel' : '撤回申请'}</button></div>}
    {orders.length > 0 && <section className="membership-orders"><h3>{en ? 'Membership requests' : '开通申请记录'}</h3>{orders.map(order => <div key={order.id}><span>{activePlanName(plans.find(plan => plan.code === order.plan_code)) || order.plan_code}</span><b>¥{(order.amount_fen / 100).toFixed(2)}</b><small>{order.status === 'requested' ? (en ? 'Pending' : '待确认') : order.status === 'fulfilled' ? (en ? 'Activated' : '已开通') : (en ? 'Cancelled' : '已撤回')} · {new Date(order.created_at).toLocaleDateString(en ? 'en-US' : 'zh-CN')}</small>{order.status === 'requested' && <button type="button" disabled={busy !== ''} onClick={() => cancelRequest(order)}>{en ? 'Cancel request' : '撤回'}</button>}</div>)}</section>}
    {message && <div className="success-line"><Check size={17}/>{message}</div>}{error && <div className="error-line">{error}</div>}
    {!loading && <section className="membership-selector">
      <div><h2>{en ? 'Choose a membership plan' : '选择适合你的会员套餐'}</h2><p>{en ? 'Compare the included monthly transcription time and validity.' : '先选版本，再对比有效期、听写额度与并发处理数。'}</p></div>
      <div className="tier-switch" role="tablist" aria-label={en ? 'Membership tier' : '会员版本'}><button type="button" role="tab" aria-selected={tier === 'standard'} className={tier === 'standard' ? 'active' : ''} onClick={() => setTier('standard')}>{en ? 'Standard' : '标准版'}</button><button type="button" role="tab" aria-selected={tier === 'professional'} className={tier === 'professional' ? 'active' : ''} onClick={() => setTier('professional')}>{en ? 'Professional' : '专业版'}</button></div>
      <div className="tier-description"><div><b>{tier === 'standard' ? (en ? 'PRO for individual creators' : 'PRO · 适合个人创作者') : (en ? 'Ultra for high-volume work' : 'Ultra · 适合高频与团队使用')}</b><p>{tier === 'standard' ? (en ? 'A balanced option for regular video research and content creation.' : '适合日常视频研究与内容创作，在额度和价格之间保持平衡。') : (en ? 'More monthly transcription time and concurrency for demanding workflows.' : '更高听写额度和并发任务数，适合密集处理与团队工作流。')}</p></div><span>{tier === 'standard' ? (en ? 'CREATOR' : '独立创作者') : (en ? 'TEAM & PRO' : '团队与高频用户')}</span></div>
    </section>}
    {loading ? <div className="membership-loading"><LoaderCircle className="spin"/>{en ? 'Loading plans…' : '正在读取套餐…'}</div> : <div className="membership-plans">
      {tier === 'standard' && plans.filter(plan => plan.code === 'free').map(plan => {
        const isCurrent = currentCode === plan.code
        return <article className="membership-plan free-plan" key={plan.code}><h2>{en ? 'Free trial' : '免费体验'}</h2><div className="plan-price"><b>¥0</b><span>/{en ? 'included' : '免费'}</span></div><p className="plan-summary">{en ? 'Try the workflow before choosing a paid plan.' : '先体验完整工作流，再按使用量升级。'}</p><ul><li><Check size={16}/>{quotaLabel(plan)}</li><li><Check size={16}/>{plan.concurrency_limit} {en ? 'concurrent tasks' : '个并发任务'}</li><li><Check size={16}/>{en ? 'AI summary' : 'AI 总结'}：{aiQuota(plan,'summary')}</li><li><Check size={16}/>{en ? 'Highlights / script rewrite' : '亮点提取 / 脚本改写'}：{aiQuota(plan,'highlights')}</li></ul><button type="button" className="outline" disabled>{isCurrent ? (en ? 'Current plan' : '当前套餐') : (en ? 'Free plan' : '免费体验')}</button></article>
      })}
      {tierPlans.map(plan => {
        const isCurrent = currentCode === plan.code
        const displayName = activePlanName(plan)
        const price = plan.price_fen == null ? '—' : plan.price_fen === 0 ? '0' : (plan.price_fen / 100).toFixed(2).replace(/\.00$/, '')
        const canRequest = plan.code !== 'free' && !isCurrent && !activeRequest
        return <article className={`membership-plan ${plan.code === 'pro_yearly' || plan.code === 'ultra_yearly' ? 'featured' : ''}`} key={plan.code}>
          {(plan.code === 'pro_yearly' || plan.code === 'ultra_yearly') && <span className="plan-badge">{en ? 'POPULAR' : '人气推荐'}</span>}
          <h2>{displayName}</h2><div className="plan-price"><b>¥{price}</b><span>{termLabel(plan)}</span></div>
          <p className="plan-summary">{quotaLabel(plan)} · {plan.concurrency_limit} {en ? 'concurrent tasks' : '个并发任务'}</p>
          <ul><li><Check size={16}/>{quotaLabel(plan)}</li><li><Check size={16}/>{plan.max_video_minutes > 0 ? `${plan.max_video_minutes} ${en ? 'min max per video' : '分钟单条上限'}` : (en ? 'No per-video duration limit' : '单条时长不限')}</li><li><Check size={16}/>{plan.concurrency_limit} {en ? 'concurrent tasks' : '个并发任务'}</li><li><Check size={16}/>{en ? 'AI summary' : 'AI 总结'}：{aiQuota(plan,'summary')}</li><li><Check size={16}/>{en ? 'AI highlights' : 'AI 亮点提取'}：{aiQuota(plan,'highlights')}</li><li><Check size={16}/>{en ? 'Visual analysis' : '画面分析'}：{aiQuota(plan,'visual')}</li><li><Check size={16}/>{en ? 'Script rewriting' : '脚本改写'}：{aiQuota(plan,'rewrite')}</li><li><Check size={16}/>{en ? 'Translation' : '多语言翻译'}：{aiQuota(plan,'translate')}</li><li><Check size={16}/>{en ? 'Video/audio and cover downloads' : '视频、音频与封面下载'}</li><li><Check size={16}/>{en ? 'Transcript editing and export' : '文案编辑与导出'}</li></ul>
          <button type="button" className={isCurrent ? 'outline' : 'primary'} disabled={isCurrent || (!canRequest && plan.code !== 'free') || busy !== ''} onClick={() => canRequest && apply(plan)}>{isCurrent ? (en ? 'Current plan' : '当前套餐') : activeRequest ? (en ? 'Request pending' : '已有待处理申请') : busy === plan.code ? (en ? 'Submitting…' : '正在提交…') : (en ? 'Request activation' : '申请开通')}</button>
        </article>
      })}
    </div>}
    <p className="membership-footnote">{en ? 'Activation requests do not collect payment. Please wait for an administrator to confirm payment outside the app before activation.' : '申请开通不会自动扣款或付款。请先按管理员提供的方式完成收款确认，再由管理员开通；页面暂未接入在线支付。'}</p>
  </main>
}

function BenefitsPage({ lang, onBack, onUpgrade }) {
  const [billing, setBilling] = useState(null)
  const [loading, setLoading] = useState(true)
  const en = lang === 'en'
  useEffect(() => { api.billing().then(setBilling).catch(console.error).finally(() => setLoading(false)) }, [])
  const quota = billing?.plan?.monthly_minutes ?? 0
  const remaining = billing?.remaining_minutes ?? 0
  const used = billing?.used_minutes ?? 0
  const progress = billing?.unlimited || quota < 0 ? 0 : Math.min(100, Math.max(0, used / Math.max(1, quota) * 100))
  const planNames = en ? {free:'Free trial',pro_monthly:'PRO Monthly',pro_yearly:'PRO Yearly',pro_lifetime:'PRO Lifetime',ultra_monthly:'Ultra Monthly',ultra_quarterly:'Ultra Quarterly',ultra_yearly:'Ultra Yearly',creator:'Creator monthly',studio:'Team monthly',legacy:'Early access',admin:'Administrator'} : {}
  const apiEnabled = billing?.plan?.code?.startsWith('ultra_')
  const fmtDate = value => value ? new Date(value).toLocaleDateString(en ? 'en-US' : 'zh-CN') : (en ? 'Not activated' : '未开通')
  return <main className="benefits-page shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>{en ? 'Back to workspace' : '返回工作台'}</button>
    <header className="benefits-heading"><h1>{en ? 'Account benefits' : '账号权益'}</h1><p>{en ? 'Review your current plan, usage, and available features.' : '查看当前会员等级、本周期剩余权益与可用功能。'}</p></header>
    {loading ? <div className="membership-loading"><LoaderCircle className="spin"/>{en ? 'Loading benefits…' : '正在读取权益…'}</div> : billing && <>
      <section className="benefit-plan-card">
        <div className="benefit-level"><span className="benefit-level-icon"><Crown size={23}/></span><div><small>{en ? 'CURRENT PLAN' : '当前等级'}</small><h2>{planNames[billing.plan.code] || billing.plan.name}</h2></div></div>
        <div className="benefit-expiry"><small>{en ? 'Expires' : '到期时间'}</small><b>{!billing.expires_at ? (en ? 'No expiration' : '无到期时间') : fmtDate(billing.expires_at)}</b></div>
        <button type="button" className="primary" onClick={onUpgrade}>{en ? 'Upgrade plan' : '升级会员'}</button>
        <div className="benefit-concurrency">{en ? 'Concurrent tasks' : '最大可同时处理数'}：<b>{billing.plan.concurrency_limit}</b></div>
      </section>
      <section className="benefit-section"><h2>{en ? 'Usage benefits' : '用量权益'}</h2>
        <div className="benefit-usage-row"><div><b>{en ? 'Video transcription' : '视频转文本'}</b><small>{billing.unlimited ? (en ? 'Unlimited' : '不限量') : `${quota} ${en ? 'min / month' : '分钟/月'}`}</small></div><strong>{billing.unlimited ? (en ? 'Unlimited' : '不限量') : `${remaining} / ${quota} ${en ? 'min left' : '分钟剩余'}`}</strong>{!billing.unlimited && <div className="benefit-progress"><i style={{width:`${progress}%`}}/></div>}</div>
        <div className="benefit-ai-usage">{[['summary','AI 总结'],['highlights','亮点提取'],['visual','画面分析'],['rewrite','脚本改写'],['translate','多语言翻译']].map(([key,label])=>{const item=billing.ai_usage?.[key]||{limit:0,used:0,remaining:0};const pct=item.limit<0?100:item.limit?Math.min(100,item.used/item.limit*100):0;return <div className="benefit-usage-row" key={key}><div><b>{label}</b><small>{item.limit<0?'不限次数':item.limit===0?'当前套餐未包含':`${item.limit} 次/月`}</small></div><strong>{item.limit<0?'不限次':`${item.remaining} / ${item.limit} 次剩余`}</strong>{item.limit!==0&&item.limit>0&&<div className="benefit-progress"><i style={{width:`${pct}%`}}/></div>}</div>})}</div>
      </section>
      <section className="benefit-section"><h2>{en ? 'Included tools' : '功能权益'}</h2><div className="benefit-feature-grid">
        {[[en?'Local video/audio upload':'本地视频与音频上传',true],[en?'Transcript editing and export':'文案编辑与导出',true],[en?'Video and audio download':'视频与音频下载',true],[en?'Highlights and visual analysis':'找亮点与画面分析',true],[en?'Script rewriting':'脚本改写',true],[en?'API access':'API 接入',apiEnabled]].map(([label,enabled])=><div className={enabled?'enabled':'unavailable'} key={label}><span>{enabled?<Check size={16}/>:<X size={16}/>}</span><div><b>{label}</b><small>{label === (en?'API access':'API 接入') ? (apiEnabled ? (en?'Available with Ultra':'Ultra 专业版可用') : (en?'Included with Ultra':'Ultra 专业版可用')) : enabled?(en?'Available on every plan':'当前套餐可用'):(en?'Not available yet':'暂未开放')}</small></div></div>)}
      </div></section>
    </>}
  </main>
}

function APIKeysPage({ lang, onBack }) {
  const [keys, setKeys] = useState([])
  const [name, setName] = useState('')
  const [createdKey, setCreatedKey] = useState('')
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const en = lang === 'en'
  const load = useCallback(() => api.apiKeys().then(setKeys), [])
  useEffect(() => { load().catch(err => setError(err.message)).finally(() => setLoading(false)) }, [load])
  const create = async event => {
    event.preventDefault(); setBusy(true); setError(''); setMessage('')
    try { const result = await api.createApiKey(name); setCreatedKey(result.key); setName(''); await load() }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const revoke = async row => {
    if (!window.confirm(en ? `Revoke “${row.name}”? Apps using this key will stop working.` : `撤销“${row.name}”？使用此密钥的程序将无法继续调用接口。`)) return
    setBusy(true); setError(''); setMessage('')
    try { await api.revokeApiKey(row.id); await load(); setMessage(en ? 'API Key revoked.' : 'API Key 已撤销。') }
    catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const copy = async () => { try { await navigator.clipboard.writeText(createdKey); setMessage(en ? 'Copied to clipboard.' : '已复制到剪贴板。') } catch { setMessage(en ? 'Select and copy the key manually.' : '请手动选中并复制密钥。') } }
  return <main className="api-keys-page shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>{en ? 'Back to workspace' : '返回工作台'}</button>
    <header className="api-keys-heading"><span><KeyRound size={20}/></span><div><h1>API Key</h1><p>{en ? 'Create and revoke keys for the Tingjian transcription API.' : '创建和撤销用于听见听写 API 的访问密钥。'}</p></div></header>
    <section className="api-key-note"><b>{en ? 'Ultra membership feature' : 'Ultra 专业版权益'}</b><p>{en ? 'Keys are shown only once. Store them securely and send them as a Bearer token. Never put a secret key in browser code.' : '密钥只会在创建时完整显示一次，请妥善保存，并通过 Authorization: Bearer 方式调用。不要把密钥写进网页前端代码。'}</p><code>POST /api/v1/tasks · GET /api/v1/tasks/&#123;task_id&#125;</code></section>
    {createdKey && <section className="api-key-created"><div><b>{en ? 'Copy your new key now' : '请立即复制新密钥'}</b><p>{en ? 'For security, it will not be shown again.' : '出于安全考虑，之后无法再次查看完整密钥。'}</p></div><code>{createdKey}</code><button type="button" className="outline" onClick={copy}><Copy size={16}/>{en ? 'Copy' : '复制'}</button><button type="button" className="icon-button" aria-label={en ? 'Dismiss' : '关闭'} onClick={() => setCreatedKey('')}><X size={17}/></button></section>}
    <form className="api-key-create" onSubmit={create}><label htmlFor="api-key-name">{en ? 'Key name' : '密钥名称'}</label><input id="api-key-name" value={name} maxLength={80} onChange={event => setName(event.target.value)} placeholder={en ? 'e.g. Production integration' : '例如：生产环境集成'}/><button type="submit" className="primary" disabled={busy}>{busy ? <LoaderCircle className="spin" size={17}/> : <KeyRound size={17}/>} {en ? 'Create API Key' : '创建 API Key'}</button></form>
    {message && <p className="success-line"><Check size={16}/>{message}</p>}{error && <p className="error-line">{error}</p>}
    <section className="api-key-list"><h2>{en ? 'Your keys' : '你的密钥'} <small>{keys.filter(row => !row.revoked_at).length}/5</small></h2>{loading ? <div className="membership-loading"><LoaderCircle className="spin"/>{en ? 'Loading keys…' : '正在读取密钥…'}</div> : keys.length ? keys.map(row => <article key={row.id}><span className="api-key-icon"><KeyRound size={18}/></span><div className="api-key-meta"><b>{row.name}</b><code>{row.prefix}••••••••••••</code><small>{en ? 'Created' : '创建于'} {new Date(row.created_at).toLocaleString(en ? 'en-US' : 'zh-CN')}{row.last_used_at && ` · ${en ? 'Last used' : '最近使用'} ${new Date(row.last_used_at).toLocaleString(en ? 'en-US' : 'zh-CN')}`}</small></div>{row.revoked_at ? <span className="api-key-revoked">{en ? 'Revoked' : '已撤销'}</span> : <button className="outline" type="button" disabled={busy} onClick={() => revoke(row)}><Trash2 size={16}/>{en ? 'Revoke' : '撤销'}</button>}</article>) : <p className="api-key-empty">{en ? 'No API Keys yet.' : '还没有 API Key。'}</p>}</section>
  </main>
}

function SettingsPage({ onBack, user, adminView = false }) {
  const [form, setForm] = useState(null)
  const [users, setUsers] = useState([])
  const [plans, setPlans] = useState([])
  const [billingOrders, setBillingOrders] = useState([])
  const [planSelections, setPlanSelections] = useState({})
  const [planDays, setPlanDays] = useState({})
  const [douyinCookies, setDouyinCookies] = useState(null)
  const [cookieBusy, setCookieBusy] = useState(false)
  const [newUser, setNewUser] = useState({username: '', password: ''})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [passwords, setPasswords] = useState({current: '', next: ''})
  const applySiliconFlowPreset = model => setForm(current => ({...current, asr_provider: 'siliconflow', siliconflow_base_url: 'https://api.siliconflow.cn/v1', siliconflow_model: model}))
  useEffect(() => {
    if (user?.role !== 'admin' || !adminView) { setForm({}); return }
    Promise.all([api.providerSettings(), api.adminUsers(), api.douyinCookieStatus(), api.adminPlans(), api.adminBillingOrders()]).then(([settings, accounts, cookieStatus, planRows, orderRows]) => { setForm(settings); setUsers(accounts); setDouyinCookies(cookieStatus); setPlans(planRows); setBillingOrders(orderRows) }).catch(err => setError(err.message))
  }, [user, adminView])
  const set = (key, value) => setForm(current => ({...current, [key]: value}))
  const save = async (event) => {
    event.preventDefault(); setBusy(true); setMessage(''); setError('')
    try {
      const payload = {...form}
      delete payload.mimo_api_key_configured; delete payload.siliconflow_api_key_configured; delete payload.custom_asr_api_key_configured; delete payload.assemblyai_api_key_configured; delete payload.tencent_secret_id_configured; delete payload.tencent_secret_key_configured; delete payload.sub2api_api_key_configured; delete payload.sub2api_fallback_api_key_configured
      setForm(await api.saveProviderSettings(payload)); setMessage('接口设置已安全保存，新任务会立即使用。')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const changePassword = async () => {
    setBusy(true); setMessage(''); setError('')
    try {
      await api.changePassword(passwords.current, passwords.next)
      setPasswords({current: '', next: ''}); setMessage('登录密码已更新。')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const createAccount = async () => {
    setBusy(true); setMessage(''); setError('')
    try {
      const account = await api.createUser(newUser.username, newUser.password)
      setUsers(current => [...current, account]); setNewUser({username: '', password: ''}); setMessage(`已创建账号 ${account.username}，请把初始密码安全发给朋友。`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const deleteAccount = async account => {
    const confirmed = window.confirm('确定永久删除账号“' + account.username + '”吗？该账号的任务记录、听写稿、AI 结果和临时媒体也会一并删除，且无法恢复。存在账单记录的账号为保留财务审计信息不会删除。')
    if (!confirmed) return
    setBusy(true); setMessage(''); setError('')
    try {
      await api.deleteUser(account.id)
      setUsers(current => current.filter(item => item.id !== account.id))
      setMessage('账号 ' + account.username + ' 及其数据已删除。')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const savePlan = async plan => {
    setBusy(true); setMessage(''); setError('')
    try {
      const saved = await api.savePlan(plan.code, {name: plan.name, tier: plan.tier, term_days: plan.term_days, price_fen: plan.price_fen, monthly_minutes: plan.monthly_minutes, max_video_minutes: plan.max_video_minutes, concurrency_limit: plan.concurrency_limit, ai_summary_limit: plan.ai_summary_limit, ai_highlights_limit: plan.ai_highlights_limit, ai_visual_limit: plan.ai_visual_limit, ai_rewrite_limit: plan.ai_rewrite_limit, ai_translate_limit: plan.ai_translate_limit, is_active: plan.is_active})
      setPlans(current => current.map(item => item.code === saved.code ? {...item, ...saved} : item))
      setMessage(`${saved.name} 套餐已保存。`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const fulfillOrder = async order => {
    setBusy(true); setMessage(''); setError('')
    try {
      await api.fulfillBillingOrder(order.id)
      setBillingOrders(current => current.filter(item => item.id !== order.id))
      setUsers(await api.adminUsers())
      setMessage(`已为 ${order.username} 开通 ${order.plan_name}，请仅在确认收款后执行。`)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const updatePlan = (code, key, value) => setPlans(current => current.map(plan => plan.code === code ? {...plan, [key]: value} : plan))
  const assignPlan = async account => {
    setBusy(true); setMessage(''); setError('')
    try {
      const assigned = await api.assignPlan(account.id, planSelections[account.id] || account.plan_code || 'free', Number(planDays[account.id] || 30))
      setMessage(`已为 ${assigned.username} 分配${assigned.plan}。`)
      setUsers(current => current.map(item => item.id === account.id ? {...item, plan_code: planSelections[account.id] || item.plan_code} : item))
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const uploadCookies = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setCookieBusy(true); setMessage(''); setError('')
    try { setDouyinCookies(await api.uploadDouyinCookies(file)); setMessage('抖音 Cookie 已安全保存，新的抖音链接任务会自动使用。') }
    catch (err) { setError(err.message) } finally { setCookieBusy(false) }
  }
  if (!form) return <main className="loading-page"><LoaderCircle className="spin"/>{adminView ? '加载管理后台' : '加载账户设置'}</main>
  return <main className="settings-page shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>{adminView ? '返回工作台' : '返回'}</button>
    <div className="settings-heading"><SlidersHorizontal/><div><h1>{adminView ? '管理后台' : '账户设置'}</h1><p>{adminView ? '集中配置听写模型、API、用户账号和商业套餐。' : '修改登录密码；接口设置仅管理员可管理。'}</p></div></div>
    {adminView && <nav className="admin-shortcuts" aria-label="管理后台导航"><button type="button" onClick={() => document.getElementById('admin-api-asr')?.scrollIntoView({behavior:'smooth',block:'start'})}><KeyRound size={16}/>API 配置</button><button type="button" onClick={() => document.getElementById('admin-plans')?.scrollIntoView({behavior:'smooth',block:'start'})}>商业套餐</button><button type="button" onClick={() => document.getElementById('admin-billing-orders')?.scrollIntoView({behavior:'smooth',block:'start'})}>开通申请</button><button type="button" onClick={() => document.getElementById('admin-users')?.scrollIntoView({behavior:'smooth',block:'start'})}>用户管理</button><button type="button" onClick={() => document.getElementById('admin-douyin')?.scrollIntoView({behavior:'smooth',block:'start'})}>媒体服务</button></nav>}
    <form className="settings-form" onSubmit={adminView && user?.role === 'admin' ? save : event => event.preventDefault()}>
      {adminView && user?.role === 'admin' && <><section id="admin-api-asr"><div className="settings-section-title"><h2>语音听写 API</h2><p>ASR 密钥只由管理员维护，朋友无法查看。</p></div>
        <div className="field-grid">
          <label>ASR 服务<select value={form.asr_provider} onChange={e => set('asr_provider', e.target.value)}><option value="mimo">小米 MiMo</option><option value="siliconflow">硅基流动</option><option value="tencent">腾讯云 ASR（说话人标记）</option><option value="assemblyai">AssemblyAI（说话人标记）</option><option value="custom">自定义 Whisper 兼容接口</option></select></label>
          <label>识别语言<select value={form.asr_language} onChange={e => set('asr_language', e.target.value)}><option value="auto">自动识别</option><option value="zh">中文</option><option value="en">英文</option></select></label>
          {form.asr_provider === 'mimo' ? <>
            <label className="wide">MiMo Base URL<input value={form.mimo_base_url} onChange={e => set('mimo_base_url', e.target.value)}/></label>
            <label>MiMo 模型<input value={form.mimo_model} onChange={e => set('mimo_model', e.target.value)}/></label>
            <label>MiMo API Key<input type="password" value={form.mimo_api_key || ''} onChange={e => set('mimo_api_key', e.target.value)} placeholder={form.mimo_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
          </> : form.asr_provider === 'siliconflow' ? <>
            <label className="wide">硅基流动 Base URL<input value={form.siliconflow_base_url} onChange={e => set('siliconflow_base_url', e.target.value)}/></label>
            <label>模型预设<select value={form.siliconflow_model} onChange={e => applySiliconFlowPreset(e.target.value)}><option value="FunAudioLLM/SenseVoiceSmall">SenseVoice Small</option><option value="TeleAI/TeleSpeechASR">TeleSpeech ASR</option></select></label>
            <label>硅基流动 API Key<input type="password" value={form.siliconflow_api_key || ''} onChange={e => set('siliconflow_api_key', e.target.value)} placeholder={form.siliconflow_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
            <p className="settings-note wide">可选模型会自动套用硅基流动官方接口地址；输入 API Key 并保存后即可用于新任务。</p>
          </> : form.asr_provider === 'tencent' ? <>
            <label>腾讯云 AppID<input value={form.tencent_app_id || ''} onChange={e => set('tencent_app_id', e.target.value)} placeholder="例如 1250000000"/></label>
            <label>引擎<select value={form.tencent_engine_type || '16k_zh'} onChange={e => set('tencent_engine_type', e.target.value)}><option value="16k_zh">16k_zh 中文普通话（支持说话人分离）</option></select></label>
            <label>腾讯云 SecretID<input type="password" value={form.tencent_secret_id || ''} onChange={e => set('tencent_secret_id', e.target.value)} placeholder={form.tencent_secret_id_configured ? '已配置，留空保持不变' : '请输入 SecretID'}/></label>
            <label>腾讯云 SecretKey<input type="password" value={form.tencent_secret_key || ''} onChange={e => set('tencent_secret_key', e.target.value)} placeholder={form.tencent_secret_key_configured ? '已配置，留空保持不变' : '请输入 SecretKey'}/></label>
            <p className="settings-note wide">已开启说话人分离。腾讯云极速接口支持 2 小时以内音频整段识别；更长音频会自动分段。</p>
          </> : form.asr_provider === 'assemblyai' ? <>
            <label className="wide">AssemblyAI Base URL<input value={form.assemblyai_base_url} onChange={e => set('assemblyai_base_url', e.target.value)} placeholder="https://api.assemblyai.com"/></label>
            <label>模型<input value={form.assemblyai_model} onChange={e => set('assemblyai_model', e.target.value)} placeholder="universal-2"/></label>
            <label>AssemblyAI API Key<input type="password" value={form.assemblyai_api_key || ''} onChange={e => set('assemblyai_api_key', e.target.value)} placeholder={form.assemblyai_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
          </> : <>
            <label className="wide">自定义 ASR Base URL<input value={form.custom_asr_base_url} onChange={e => set('custom_asr_base_url', e.target.value)} placeholder="https://example.com/v1"/></label>
            <label>模型<input value={form.custom_asr_model} onChange={e => set('custom_asr_model', e.target.value)}/></label>
            <label>API Key<input type="password" value={form.custom_asr_api_key || ''} onChange={e => set('custom_asr_api_key', e.target.value)} placeholder={form.custom_asr_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
          </>}
        </div>
      </section>
      <section id="admin-api-copy"><div className="settings-section-title"><h2>文案 AI</h2><p>只在用户点击找亮点或复刻改编时调用 Sub2API。</p></div>
        <div className="field-grid">
          <label className="wide">Sub2API Base URL<input value={form.sub2api_base_url} onChange={e => set('sub2api_base_url', e.target.value)} placeholder="http://100.x.x.x:18081/v1"/></label>
          <label>Sub2API API Key<input type="password" value={form.sub2api_api_key || ''} onChange={e => set('sub2api_api_key', e.target.value)} placeholder={form.sub2api_api_key_configured ? '已配置，留空保持不变' : '请输入专用 API Key'}/></label>
          <label>首选模型<input value={form.llm_primary_model} onChange={e => set('llm_primary_model', e.target.value)} placeholder="Gemini 模型名"/></label>
          <label>备用模型<input value={form.llm_fallback_model} onChange={e => set('llm_fallback_model', e.target.value)} placeholder="GPT 模型名"/></label>
          <label className="wide">备用 Sub2API API Key（可选）<input type="password" value={form.sub2api_fallback_api_key || ''} onChange={e => set('sub2api_fallback_api_key', e.target.value)} placeholder={form.sub2api_fallback_api_key_configured ? '已配置，留空保持不变' : 'GPT 若属于其他分组，请填写绑定 OpenAI 分组的 Key'}/></label>
        </div>
      </section>
      <section id="admin-douyin"><div className="settings-section-title"><h2>抖音下载</h2><p>建议使用小号。可用新版 Chrome 扩展同步 Cookie 与浏览器标识，也可上传 Cookie 文件；不保存账号密码。</p></div>
        <div className="cookie-settings"><div><b>{douyinCookies?.configured ? '已配置抖音 Cookie' : '尚未配置抖音 Cookie'}</b><small>{douyinCookies?.configured ? `更新时间：${new Date(douyinCookies.updated_at).toLocaleString()}${douyinCookies.user_agent_configured ? ' · Chrome 标识已同步' : ' · 请更新扩展同步浏览器标识'}` : '抖音链接可能会提示需要新鲜 Cookie'}</small></div><label className="outline cookie-upload"><Upload size={17}/>选择 Cookie 文件<input type="file" accept=".txt,.cookies,text/plain" onChange={uploadCookies} disabled={cookieBusy}/></label></div>
        <p className="settings-note">在同一 Chrome 配置中登录抖音和听见管理后台，然后安装新版“听见抖音 Cookie 同步”扩展，从已登录的抖音页面主动同步。也可上传 Netscape 格式 Cookie 文件。</p>
      </section>
      <section id="admin-plans"><div className="settings-section-title"><h2>商业套餐</h2><p>按月统计听写分钟数；当前在线支付尚未接入，用户提交申请后由管理员确认收款并开通。</p></div>
        <div className="billing-plan-list">{plans.filter(plan => !['admin','legacy'].includes(plan.code)).map(plan => <div className="billing-plan-editor" key={plan.code}>
          <div className="billing-plan-top"><b>{plan.name}</b><code>{plan.code}</code><label><input type="checkbox" checked={plan.is_active} onChange={event => updatePlan(plan.code,'is_active',event.target.checked)}/>对用户开放</label></div>
          <div className="billing-plan-fields">
            <label>版本<select value={plan.tier || 'standard'} onChange={event => updatePlan(plan.code,'tier',event.target.value)}><option value="standard">标准版</option><option value="professional">专业版</option></select></label>
            <label>有效天数（0=永久）<input type="number" min="0" value={plan.term_days ?? 30} onChange={event => updatePlan(plan.code,'term_days',Number(event.target.value))}/></label>
            <label>售价（元）<input type="number" min="0" step="0.01" value={plan.price_fen == null ? '' : (plan.price_fen / 100)} placeholder="先填写价格" onChange={event => updatePlan(plan.code,'price_fen',event.target.value === '' ? null : Math.round(Number(event.target.value) * 100))}/></label>
            <label>每月听写分钟<input type="number" min="-1" value={plan.monthly_minutes} onChange={event => updatePlan(plan.code,'monthly_minutes',Number(event.target.value))}/></label>
            <label>单条视频上限（分钟）<input type="number" min="0" value={plan.max_video_minutes} onChange={event => updatePlan(plan.code,'max_video_minutes',Number(event.target.value))}/></label>
            <label>并发任务数<input type="number" min="1" value={plan.concurrency_limit} onChange={event => updatePlan(plan.code,'concurrency_limit',Number(event.target.value))}/></label>
            <label>AI 总结次数/月<input type="number" min="-1" value={plan.ai_summary_limit} onChange={event => updatePlan(plan.code,'ai_summary_limit',Number(event.target.value))}/></label>
            <label>亮点提取次数/月<input type="number" min="-1" value={plan.ai_highlights_limit} onChange={event => updatePlan(plan.code,'ai_highlights_limit',Number(event.target.value))}/></label>
            <label>画面分析次数/月<input type="number" min="-1" value={plan.ai_visual_limit} onChange={event => updatePlan(plan.code,'ai_visual_limit',Number(event.target.value))}/></label>
            <label>脚本改写次数/月<input type="number" min="-1" value={plan.ai_rewrite_limit} onChange={event => updatePlan(plan.code,'ai_rewrite_limit',Number(event.target.value))}/></label>
            <label>翻译次数/月<input type="number" min="-1" value={plan.ai_translate_limit} onChange={event => updatePlan(plan.code,'ai_translate_limit',Number(event.target.value))}/></label>
            <button type="button" className="outline compact" disabled={busy} onClick={() => savePlan(plan)}>保存套餐</button>
          </div>
          <small>{plan.monthly_minutes < 0 ? '不限时长' : `${plan.monthly_minutes} 分钟/月`} · {plan.term_days === 0 ? '永久有效' : `有效 ${plan.term_days} 天`} · {plan.price_fen == null ? '价格未设置' : `¥${(plan.price_fen / 100).toFixed(2)}`}</small>
        </div>)}</div>
        <p className="settings-note">填 -1 表示不限额度，视频单条上限填 0 表示不限。新价格仅影响后续申请，不改变已有订单。</p>
      </section>
      <section id="admin-billing-orders"><div className="settings-section-title"><h2>会员开通申请</h2><p>线下确认收款后再点击开通；该操作将立即写入用户的会员权益。</p></div>
        {billingOrders.length ? <div className="billing-order-list">{billingOrders.map(order => <div className="billing-order-row" key={order.id}><span><b>{order.username}</b><small>{order.plan_name} · ¥{(order.amount_fen / 100).toFixed(2)} · {new Date(order.created_at).toLocaleString()}</small></span><button type="button" className="primary compact" disabled={busy} onClick={() => fulfillOrder(order)}>确认收款并开通</button></div>)}</div> : <p className="settings-note">目前没有待处理申请。</p>}
      </section>
      <section id="admin-users"><div className="settings-section-title"><h2>用户管理</h2><p>手动创建账号，不开放陌生人注册。</p></div>
        <div className="account-create"><input value={newUser.username} onChange={e => setNewUser({...newUser, username: e.target.value})} placeholder="朋友用户名"/><input type="password" value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} placeholder="初始密码（至少 12 位）"/><button type="button" className="outline" disabled={busy || newUser.username.trim().length < 3 || newUser.password.length < 12} onClick={createAccount}>创建账号</button></div>
        <div className="user-list">{users.map(item => <div className="user-plan-row" key={item.id}><span>{item.username}<small>{item.role === 'admin' ? '管理员' : '普通用户 · ' + (plans.find(plan => plan.code === item.plan_code)?.name || '免费体验')}</small></span>{item.role !== 'admin' && <div><select value={planSelections[item.id] || item.plan_code || 'free'} onChange={event => setPlanSelections(current => ({...current,[item.id]:event.target.value}))}>{plans.filter(plan => plan.code !== 'admin' && (plan.is_active || plan.code === item.plan_code)).map(plan => <option key={plan.code} value={plan.code}>{plan.name}</option>)}</select><input type="number" min="1" max="3650" aria-label="套餐天数" value={planDays[item.id] || 30} onChange={event => setPlanDays(current => ({...current,[item.id]:event.target.value}))}/><button type="button" className="outline compact" disabled={busy || !plans.find(plan => plan.code === (planSelections[item.id] || item.plan_code || 'free'))?.is_active} onClick={() => assignPlan(item)}>分配套餐</button><button type="button" className="user-delete" aria-label={'删除账号 ' + item.username} title={'删除账号 ' + item.username} disabled={busy} onClick={() => deleteAccount(item)}>删除账号</button></div>}</div>)}</div>
      </section></>}
      <section><div className="settings-section-title"><h2>登录安全</h2><p>建议每个账号首次登录后修改初始密码。</p></div>
        <div className="field-grid"><label>当前密码<input type="password" value={passwords.current} onChange={e => setPasswords({...passwords,current:e.target.value})}/></label><label>新密码（至少 12 位）<input type="password" value={passwords.next} onChange={e => setPasswords({...passwords,next:e.target.value})}/></label></div>
        <button type="button" className="outline password-button" disabled={busy || !passwords.current || passwords.next.length < 12} onClick={changePassword}>更新登录密码</button>
      </section>
      {message && <div className="success-line"><Check size={17}/>{message}</div>}{error && <div className="error-line">{error}</div>}
      {user?.role === 'admin' && <button className="primary save-settings" disabled={busy}>{busy ? <LoaderCircle className="spin" size={18}/> : <Save size={18}/>}保存接口设置</button>}
    </form>
  </main>
}

function App() {
  const [user, setUser] = useState(undefined)
  const panelMode = ['panel.tingjian.gaoseafood.com', '100.78.228.11', 'localhost', '127.0.0.1'].includes(window.location.hostname)
  const [page, setPage] = useState(() => ['panel.tingjian.gaoseafood.com', '100.78.228.11'].includes(window.location.hostname) ? 'admin' : 'home')
  const [lang, setLang] = useState(() => window.localStorage.getItem('tingjian-language') === 'en' ? 'en' : 'zh')
  const [theme, setTheme] = useState(() => ['light', 'dark'].includes(window.localStorage.getItem('tingjian-theme')) ? window.localStorage.getItem('tingjian-theme') : 'system')
  const [tasks, setTasks] = useState([])
  const [selected, setSelected] = useState(null)
  const [importing, setImporting] = useState(false)
  const [importError, setImportError] = useState('')
  const importUrlRef = useRef(new URLSearchParams(window.location.search).get('import_url')?.trim() || '')
  const refresh = useCallback(async () => { const items = await api.tasks(); setTasks(items); return items }, [])
  useEffect(() => {
    const media = window.matchMedia('(prefers-color-scheme: dark)')
    const apply = () => {
      const resolved = theme === 'system' ? (media.matches ? 'dark' : 'light') : theme
      document.documentElement.dataset.theme = resolved
    }
    apply()
    if (theme !== 'system') return undefined
    media.addEventListener?.('change', apply)
    return () => media.removeEventListener?.('change', apply)
  }, [theme])
  const removeTask = useCallback(async (taskId) => {
    await api.deleteTask(taskId)
    setTasks(current => current.filter(task => task.id !== taskId))
    if (selected === taskId) { setSelected(null); setPage('history') }
  }, [selected])
  const importPendingUrl = useCallback(async () => {
    const importUrl = importUrlRef.current
    if (!importUrl || !user) return
    setImporting(true); setImportError('')
    try {
      const task = await api.url(importUrl)
      await refresh()
      setSelected(task.id); setPage('detail')
      const cleanUrl = new URL(window.location.href)
      cleanUrl.searchParams.delete('import_url'); cleanUrl.searchParams.delete('material_id')
      window.history.replaceState({}, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`)
      importUrlRef.current = ''
    } catch (err) {
      setImportError(`日报视频导入失败：${err.message}`)
    } finally { setImporting(false) }
  }, [refresh, user])
  useEffect(() => { api.me().then(async me => { setUser(me); await refresh() }).catch(() => setUser(null)) }, [refresh])
  const changeLanguage = value => { setLang(value); window.localStorage.setItem('tingjian-language', value) }
  const changeTheme = value => { setTheme(value); window.localStorage.setItem('tingjian-theme', value) }
  useEffect(() => { if (user) importPendingUrl() }, [user, importPendingUrl])
  useEffect(() => {
    if (!user || !tasks.some(t => !['completed','failed'].includes(t.status))) return
    const timer = setInterval(() => refresh().catch(console.error), 2200); return () => clearInterval(timer)
  }, [user, tasks, refresh])
  if (user === undefined) return <main className="loading-page"><LoaderCircle className="spin"/>加载中</main>
  if (!user) return <Login lang={lang} onLanguageChange={changeLanguage} onLogin={async me => { setUser(me); await refresh() }}/>
  const open = id => { setSelected(id); setPage('detail') }
  return <div className="app"><Header page={page} setPage={setPage} user={user} lang={lang} theme={theme} onThemeChange={changeTheme} onLanguageChange={changeLanguage} onLogout={async () => { await api.logout(); setUser(null) }} panelMode={panelMode}/>
    {page === 'home' && <Home tasks={tasks} refresh={refresh} onOpen={open} lang={lang}/>}
    {page === 'history' && <main className="shell history-page"><div className="history-heading"><History/><div><h1>{lang === 'en' ? 'History' : '历史记录'}</h1><p>{lang === 'en' ? 'Your transcripts, AI analysis, and download tasks are saved here.' : '你的听写稿、AI 分析和下载任务都保存在这里。'}</p></div></div><TaskTable tasks={tasks} onOpen={open} onDelete={removeTask} full lang={lang}/></main>}
    {page === 'membership' && <MembershipPage lang={lang} onBack={() => setPage('home')}/>}
    {page === 'benefits' && <BenefitsPage lang={lang} onBack={() => setPage('home')} onUpgrade={() => setPage('membership')}/>}
    {page === 'api-keys' && <APIKeysPage lang={lang} onBack={() => setPage('home')}/>}
    {page === 'settings' && <SettingsPage user={user} onBack={() => setPage('home')}/>}
    {page === 'admin' && panelMode && user.role === 'admin' && <SettingsPage user={user} adminView onBack={() => setPage('home')}/>}
    {page === 'admin' && (!panelMode || user.role !== 'admin') && <main className="shell access-denied"><LockKeyhole size={26}/><h1>此页面仅管理员可访问</h1><p>请从 Tailscale 管理域名使用管理员账号登录。</p><button className="outline" onClick={() => setPage('home')}>返回工作台</button></main>}
    {page === 'detail' && selected && (
      <Detail taskId={selected} onBack={() => { refresh(); setPage('home') }} refresh={refresh} onOpen={open}/>
    )}
    {importing && <div className="notice"><LoaderCircle className="spin" size={16}/>正在导入日报视频…</div>}
    {importError && <div className="notice import-error">{importError}</div>}
  </div>
}

function clock(seconds = 0) { const s = Math.max(0, Math.floor(seconds)); return `${String(Math.floor(s / 3600)).padStart(2,'0')}:${String(Math.floor((s % 3600) / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}` }
function friendlyDate(value, lang = 'zh') { if (!value) return '—'; const d = new Date(value); const today = new Date(); const locale = lang === 'en' ? 'en-US' : 'zh-CN'; return d.toDateString() === today.toDateString() ? `${lang === 'en' ? 'Today' : '今天'} ${d.toLocaleTimeString(locale,{hour:'2-digit',minute:'2-digit'})}` : d.toLocaleDateString(locale,{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) }
function sourceDate(value, lang = 'zh') { if (!value) return lang === 'en' ? 'Unknown date' : '未知日期'; const d = new Date(value); return d.toLocaleDateString(lang === 'en' ? 'en-CA' : 'zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).replace(/\//g, '-') }
function fileSize(bytes) { if (bytes < 1024**2) return `${(bytes/1024).toFixed(1)} KB`; return `${(bytes/1024**2).toFixed(1)} MB` }

export default App
