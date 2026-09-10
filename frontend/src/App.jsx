import { useCallback, useEffect, useRef, useState } from 'react'
import {
  ArrowLeft, Check, ChevronRight, Clock3, Copy, Download, FileAudio, FileVideo, Film,
  History, Link2, LoaderCircle, LockKeyhole, LogOut, PencilLine,
  Play, RotateCcw, Search, Sparkles, Trash2, Upload, UserRound, Volume2, WandSparkles,
  SlidersHorizontal, Save,
} from 'lucide-react'
import { api } from './api'

const STATUS = {
  queued: '等待中', preparing: '准备中', downloading: '下载中', transcribing: '听写中',
  completed: '已完成', failed: '失败',
}

function Logo() {
  return <div className="logo"><span className="wave"><i/><i/><i/><i/><i/></span><strong>听见</strong></div>
}

function Header({ page, setPage, user, onLogout }) {
  return <header className="header">
    <Logo />
    <nav>
      <button className={page === 'home' || page === 'detail' ? 'active' : ''} onClick={() => setPage('home')}>工作台</button>
      <button className={page === 'history' ? 'active' : ''} onClick={() => setPage('history')}>历史记录</button>
    </nav>
    <div className="account"><span><UserRound size={18}/>{user?.username}</span><button title="账户设置" onClick={() => setPage('settings')}><SlidersHorizontal size={18}/></button><button title="退出登录" onClick={onLogout}><LogOut size={18}/></button></div>
  </header>
}

function Login({ onLogin }) {
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
    <section className="login-panel">
      <Logo />
      <div><h1>欢迎回来</h1><p>登录你的私人视频听写工作台</p></div>
      <form onSubmit={submit}>
        <label>用户名<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" /></label>
        <label>密码<input type="password" value={password} onChange={e => setPassword(e.target.value)} autoComplete="current-password" autoFocus /></label>
        {error && <div className="error-line">{error}</div>}
        <button className="primary full" disabled={busy || !password}>{busy ? <LoaderCircle className="spin" size={18}/> : <LockKeyhole size={18}/>}登录</button>
      </form>
    </section>
  </main>
}

function StatusMark({ task }) {
  if (task.status === 'completed') return <span className="status success"><Check size={15}/>{STATUS[task.status]}</span>
  if (task.status === 'failed') return <span className="status failed">失败</span>
  if (['preparing','downloading','transcribing'].includes(task.status)) return <span className="status working"><LoaderCircle className="spin" size={15}/>{STATUS[task.status]} {task.progress}%</span>
  return <span className="status"><Clock3 size={15}/>{STATUS[task.status] || task.status}</span>
}

function TaskTable({ tasks, onOpen, onDelete, full = false }) {
  const remove = async (event, task) => {
    event.stopPropagation()
    if (!window.confirm(`确定删除“${task.title}”这条历史记录吗？听写稿、亮点和改写结果都会删除。`)) return
    try { await onDelete(task.id) } catch (err) { window.alert(err.message) }
  }
  return <section className={`recent ${full ? 'history-list' : ''}`}>
    <div className="section-title"><h2>{full ? '全部听写记录' : '最近听写'}</h2>{full && <span>{tasks.length} 条记录</span>}</div>
    <div className="task-table">
      <div className="task-head"><span>标题</span><span>来源</span><span>时长</span><span>状态</span><span>时间</span><span/></div>
      {tasks.length === 0 && <div className="empty">还没有听写记录，先上传一个视频吧。</div>}
      {tasks.map(task => <div className="task-row" role="button" tabIndex="0" key={task.id}
        onClick={() => onOpen(task.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') onOpen(task.id) }}>
        <span className="task-name">{task.media_kind === 'audio' ? <FileAudio size={21}/> : <FileVideo size={21}/>}<b>{task.title}</b><small>{sourceDate(task.created_at)}</small></span>
        <span>{task.source_type === 'url' ? '视频链接' : '本地文件'}</span>
        <span>{clock(task.duration)}</span><StatusMark task={task}/>
        <span>{friendlyDate(task.created_at)}</span>
        <span className="task-actions">{onDelete && <button className="task-delete" aria-label={`删除${task.title}`} onClick={event => remove(event, task)}><Trash2 size={16}/></button>}<ChevronRight size={18}/></span>
      </div>)}
    </div>
  </section>
}

function Home({ tasks, refresh, onOpen }) {
  const [file, setFile] = useState(null)
  const [input, setInput] = useState('')
  const [drag, setDrag] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const inputRef = useRef(null)
  const submit = async () => {
    setBusy(true); setError('')
    try {
      const task = file ? await api.upload(file) : await api.url(input)
      await refresh(); onOpen(task.id)
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const choose = (selected) => { if (selected) { setFile(selected); setError('') } }
  return <main className="home shell">
    <section className="hero-copy">
      <h1>把视频，变成可编辑的文字</h1>
      <p>粘贴视频链接或分享文案，也可以直接上传视频、音频，先完成听写，再决定下一步。</p>
    </section>
    <div className={`unified-input ${drag ? 'drag' : ''} ${file ? 'has-file' : ''}`}
      onDragOver={e => { e.preventDefault(); setDrag(true) }} onDragLeave={() => setDrag(false)}
      onDrop={e => { e.preventDefault(); setDrag(false); choose(e.dataTransfer.files[0]) }}>
      <Link2 size={24} className="unified-input-icon" />
      <input value={file ? file.name : input} onChange={e => { setInput(e.target.value); setFile(null) }} placeholder="粘贴视频链接或整段分享文案…" aria-label="视频链接或分享文案" />
      <input ref={inputRef} type="file" accept="video/*,audio/*" hidden onChange={e => choose(e.target.files[0])}/>
      <button type="button" className="upload-button" onClick={() => inputRef.current?.click()}><Upload size={18}/>上传</button>
      {file && <span className="file-pill">{file.type.startsWith('audio/') ? <FileAudio size={16}/> : <FileVideo size={16}/>} {fileSize(file.size)}</span>}
    </div>
    <p className="unified-hint">支持 MP4、MOV、MKV、WebM、MP3、WAV、M4A，单个文件最大 2GB；也支持直接拖入文件</p>
    <div className="submit-row"><button className="primary" disabled={busy || (!file && !input.trim())} onClick={submit}>
      {busy ? <LoaderCircle className="spin" size={20}/> : <span className="mini-wave"><i/><i/><i/></span>}开始听写
    </button><span>{busy ? '正在上传并创建任务…' : '只进行语音听写，不会自动调用 AI；长视频会自动切换为音频模式。'}</span></div>
    {error && <div className="error-line spacious">{error}</div>}
    <TaskTable tasks={tasks.slice(0, 5)} onOpen={onOpen}/>
  </main>
}

function TranscriptEditor({ segments, showTimes, onChange }) {
  const value = segments.map(segment => showTimes ? `[${segment.start}] ${segment.text}` : segment.text).join('\n')
  const edit = event => {
    const lines = event.target.value.split(/\r?\n/)
    onChange(lines.map((line, index) => {
      const base = segments[index] || { start: '', end: '', start_seconds: 0, end_seconds: 0 }
      const text = showTimes ? line.replace(/^\s*\[?\d{1,2}:\d{2}(?::\d{2})?\]?\s*/, '') : line
      return {...base, text}
    }))
  }
  return <div className="transcript-editor"><textarea value={value} onChange={edit} spellCheck="false" placeholder="听写内容会显示在这里…" /></div>
}

function HighlightResults({ items }) {
  return <div className="ai-results"><div className="result-heading"><Sparkles size={18}/><b>找到 {items.length} 个亮点</b></div>
    {items.map((item, index) => <article className="highlight" key={index}>
      <div><span className="score">{item.score || 8}</span><b>{item.title || `亮点 ${index + 1}`}</b><small>{item.start}–{item.end}</small></div>
      <blockquote>{item.original_text}</blockquote><p>{item.reason}</p>
    </article>)}
  </div>
}

function VisualResults({ items }) {
  return <div className="visual-results"><div className="result-heading"><Film size={18}/><b>画面分析</b><small>{items.length} 个关键画面</small></div>
    {items.map((item, index) => <article className="visual-item" key={index}>
      <div><b>{item.timestamp || `画面 ${index + 1}`}</b><span>{item.suggested_use || '视觉信息'}</span></div>
      <p>{item.description || '未提供画面描述'}</p>
      {item.onscreen_text && <small>画面文字：{item.onscreen_text}</small>}
      {item.visual_hook && <small>亮点：{item.visual_hook}</small>}
    </article>)}
  </div>
}

function Detail({ taskId, onBack, onSettings }) {
  const [task, setTask] = useState(null)
  const [segments, setSegments] = useState([])
  const [search, setSearch] = useState('')
  const [showTimes, setShowTimes] = useState(true)
  const [dirty, setDirty] = useState(false)
  const [direction, setDirection] = useState('')
  const [action, setAction] = useState(null)
  const [notice, setNotice] = useState('')
  const mediaRef = useRef(null)
  const load = useCallback(async () => {
    const next = await api.task(taskId); setTask(next)
    if (!dirty) setSegments(next.segments || [])
  }, [taskId, dirty])
  useEffect(() => { load().catch(console.error) }, [load])
  useEffect(() => {
    const visualRunning = task && !['idle', 'completed', 'failed'].includes(task.visual_status || 'idle')
    const aiRunning = task && !['idle', 'failed'].includes(task.ai_status)
    if (!task || (task.status === 'completed' && !aiRunning && !visualRunning) || task.status === 'failed') return
    const timer = setInterval(() => load().catch(console.error), 1800); return () => clearInterval(timer)
  }, [task, load])
  const save = async () => { setTask(await api.saveTranscript(taskId, segments)); setDirty(false); setNotice('已保存修改') }
  const startHighlights = async () => {
    setAction('highlights'); setNotice('')
    try { await api.highlights(taskId); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const startVisualAnalysis = async () => {
    setAction('visual'); setNotice('')
    try { await api.visualAnalysis(taskId); await load() }
    catch (err) { setAction(null); setNotice(err.message) }
  }
  const startRewrite = async () => {
    setAction('rewrite'); setNotice('')
    try { await api.rewrite(taskId, direction); await load() }
    catch (err) { setAction('rewrite'); setNotice(err.message) }
  }
  if (!task) return <main className="loading-page"><LoaderCircle className="spin"/>加载中</main>
  if (task.status !== 'completed') return <main className="processing shell"><button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button><div className="processing-center">
    {task.status === 'failed' ? <><span className="process-icon failed"><RotateCcw/></span><h1>听写失败</h1><p>{task.error}</p></> : <><span className="process-icon"><LoaderCircle className="spin"/></span><h1>{task.message}</h1><p>{task.title}</p><div className="big-progress"><i style={{width: `${task.progress}%`}}/></div><b>{task.progress}%</b></>}
  </div></main>
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
  const running = !['idle','failed'].includes(task.ai_status) || visualRunning
  return <main className="detail shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button>
    <div className="detail-head"><div><h1>{task.title} <small className="title-date">· {sourceDate(task.created_at)}</small></h1><p>{clock(task.duration)} · 中文 · {task.asr_provider === 'mimo' ? 'MiMo-V2.5-ASR' : '自定义 ASR'} · 听写完成</p></div>
      <div><a className="outline" href={`/api/tasks/${task.id}/export/txt`}><Download size={18}/>导出</a></div></div>
    <div className="workspace">
      <section className={`transcript-pane ${showTimes ? '' : 'hide-times'}`}>
        <div className="pane-title"><h2>听写原文</h2><label className="switch-label">显示时间码<input type="checkbox" checked={showTimes} onChange={e => setShowTimes(e.target.checked)}/><i/></label></div>
        <div className="transcript-tools"><label><Search size={18}/><input value={search} onChange={e => setSearch(e.target.value)} placeholder="搜索文案" /></label>
          <button className="outline compact" onClick={() => navigator.clipboard.writeText(segments.map(x => x.text).join('\n'))}><Copy size={17}/>复制全文</button>
          <a className="outline compact" href={`/api/tasks/${task.id}/export/txt`}><Download size={17}/>TXT</a>
          <a className="outline compact" href={`/api/tasks/${task.id}/export/srt`}><Download size={17}/>SRT</a>
          {dirty && <button className="primary compact" onClick={save}>保存修改</button>}
        </div>
        <TranscriptEditor segments={visible} showTimes={showTimes} onChange={updateVisible}/>
        {task.source_available ? task.media_kind === 'audio' ? <audio ref={mediaRef} className="media-player audio-player" controls src={`/api/tasks/${task.id}/media`} /> : <video ref={mediaRef} className="media-player" controls src={`/api/tasks/${task.id}/media`} /> : <div className="media-missing">原媒体已按策略删除，听写稿仍会保留。</div>}
      </section>
      <aside className="next-pane">
        <div><h2>下一步</h2><p>听写已完成。需要时再调用 AI，不会自动消耗额度。</p></div>
        <article className="action-row"><span className="action-icon coral"><WandSparkles/></span><div><h3>找亮点</h3><p>提取时间点、原话、推荐理由和标题</p></div><button className="primary compact" disabled={running} onClick={startHighlights}>{task.ai_status === 'highlighting' ? '分析中…' : '开始分析'}</button></article>
        <article className="action-row visual-action"><span className="action-icon"><Film/></span><div><h3>分析画面</h3><p>识别关键帧、画面文字、场景和视觉吸引力</p></div><button className="outline compact" disabled={running || task.media_kind === 'audio' || !task.source_available || ['queued','analyzing'].includes(task.visual_status)} onClick={startVisualAnalysis}>{['queued','analyzing'].includes(task.visual_status) ? '分析中…' : task.media_kind === 'audio' ? '仅视频支持' : task.visual_status === 'completed' ? '重新分析' : task.source_available ? '开始分析' : '原视频已删除'}</button></article>
        <article className="action-row rewrite"><span className="action-icon"><PencilLine/></span><div><h3>复刻改编</h3><p>保留结构与节奏，生成新的口播文案</p></div><button className="outline compact coral-text" disabled={running} onClick={() => setAction('rewrite')}>开始改编</button></article>
        {action === 'rewrite' && <div className="rewrite-form"><label>改编方向<textarea value={direction} onChange={e => setDirection(e.target.value)} placeholder="例如：改成面向新手的 60 秒口播，语气自然、有反差感"/></label><button className="primary compact" disabled={running} onClick={startRewrite}>生成新文案</button></div>}
        {running && <div className="ai-running"><LoaderCircle className="spin" size={18}/>{task.ai_message}</div>}
        {task.ai_status === 'failed' && <div className="error-line">{task.ai_message}</div>}
        {task.highlights?.length > 0 && <HighlightResults items={task.highlights}/>} 
        {task.visual_analysis?.length > 0 && <VisualResults items={task.visual_analysis}/>}
        {task.rewrite_text && <div className="rewrite-result"><div className="result-heading"><PencilLine size={18}/><b>改编结果</b><button onClick={() => navigator.clipboard.writeText(task.rewrite_text)}><Copy size={16}/>复制</button></div><pre>{task.rewrite_text}</pre></div>}
        <div className="ai-settings"><div><h3>AI 设置</h3><button onClick={onSettings}>更改</button></div><p><span className="gemini-mark">✦</span>首选 <b>Gemini</b></p><p><span className="gpt-mark">◎</span>备用 <b>GPT</b></p></div>
        <div className="retention"><span>原视频将在 24 小时后自动删除</span>{task.source_available && <button onClick={async () => { if(confirm('立即删除原视频？听写稿会保留。')) { await api.deleteSource(task.id); load() } }}><Trash2 size={16}/>立即删除</button>}</div>
        {notice && <div className="notice">{notice}</div>}
      </aside>
    </div>
  </main>
}

function SettingsPage({ onBack, user }) {
  const [form, setForm] = useState(null)
  const [users, setUsers] = useState([])
  const [newUser, setNewUser] = useState({username: '', password: ''})
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const [passwords, setPasswords] = useState({current: '', next: ''})
  useEffect(() => {
    if (user?.role !== 'admin') { setForm({}); return }
    Promise.all([api.providerSettings(), api.adminUsers()]).then(([settings, accounts]) => { setForm(settings); setUsers(accounts) }).catch(err => setError(err.message))
  }, [user])
  const set = (key, value) => setForm(current => ({...current, [key]: value}))
  const save = async (event) => {
    event.preventDefault(); setBusy(true); setMessage(''); setError('')
    try {
      const payload = {...form}
      delete payload.mimo_api_key_configured; delete payload.custom_asr_api_key_configured; delete payload.sub2api_api_key_configured; delete payload.sub2api_fallback_api_key_configured
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
  if (!form) return <main className="loading-page"><LoaderCircle className="spin"/>加载接口设置</main>
  return <main className="settings-page shell">
    <button className="back" onClick={onBack}><ArrowLeft size={18}/>返回工作台</button>
    <div className="settings-heading"><SlidersHorizontal/><div><h1>{user?.role === 'admin' ? '管理员设置' : '账户设置'}</h1><p>{user?.role === 'admin' ? '只有你能修改 ASR、Sub2API 和模型设置。' : '你可以修改自己的登录密码，不能查看管理员接口设置。'}</p></div></div>
    <form className="settings-form" onSubmit={user?.role === 'admin' ? save : event => event.preventDefault()}>
      {user?.role === 'admin' && <><section><div className="settings-section-title"><h2>语音听写</h2><p>ASR 密钥只由管理员维护，朋友无法查看。</p></div>
        <div className="field-grid">
          <label>ASR 服务<select value={form.asr_provider} onChange={e => set('asr_provider', e.target.value)}><option value="mimo">小米 MiMo</option><option value="custom">自定义 Whisper 兼容接口</option></select></label>
          <label>识别语言<select value={form.asr_language} onChange={e => set('asr_language', e.target.value)}><option value="auto">自动识别</option><option value="zh">中文</option><option value="en">英文</option></select></label>
          {form.asr_provider === 'mimo' ? <>
            <label className="wide">MiMo Base URL<input value={form.mimo_base_url} onChange={e => set('mimo_base_url', e.target.value)}/></label>
            <label>MiMo 模型<input value={form.mimo_model} onChange={e => set('mimo_model', e.target.value)}/></label>
            <label>MiMo API Key<input type="password" value={form.mimo_api_key || ''} onChange={e => set('mimo_api_key', e.target.value)} placeholder={form.mimo_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
          </> : <>
            <label className="wide">自定义 ASR Base URL<input value={form.custom_asr_base_url} onChange={e => set('custom_asr_base_url', e.target.value)} placeholder="https://example.com/v1"/></label>
            <label>模型<input value={form.custom_asr_model} onChange={e => set('custom_asr_model', e.target.value)}/></label>
            <label>API Key<input type="password" value={form.custom_asr_api_key || ''} onChange={e => set('custom_asr_api_key', e.target.value)} placeholder={form.custom_asr_api_key_configured ? '已配置，留空保持不变' : '请输入 API Key'}/></label>
          </>}
        </div>
      </section>
      <section><div className="settings-section-title"><h2>文案 AI</h2><p>只在用户点击找亮点或复刻改编时调用 Sub2API。</p></div>
        <div className="field-grid">
          <label className="wide">Sub2API Base URL<input value={form.sub2api_base_url} onChange={e => set('sub2api_base_url', e.target.value)} placeholder="http://100.x.x.x:18081/v1"/></label>
          <label>Sub2API API Key<input type="password" value={form.sub2api_api_key || ''} onChange={e => set('sub2api_api_key', e.target.value)} placeholder={form.sub2api_api_key_configured ? '已配置，留空保持不变' : '请输入专用 API Key'}/></label>
          <label>首选模型<input value={form.llm_primary_model} onChange={e => set('llm_primary_model', e.target.value)} placeholder="Gemini 模型名"/></label>
          <label>备用模型<input value={form.llm_fallback_model} onChange={e => set('llm_fallback_model', e.target.value)} placeholder="GPT 模型名"/></label>
          <label className="wide">备用 Sub2API API Key（可选）<input type="password" value={form.sub2api_fallback_api_key || ''} onChange={e => set('sub2api_fallback_api_key', e.target.value)} placeholder={form.sub2api_fallback_api_key_configured ? '已配置，留空保持不变' : 'GPT 若属于其他分组，请填写绑定 OpenAI 分组的 Key'}/></label>
        </div>
      </section>
      <section><div className="settings-section-title"><h2>朋友账号</h2><p>手动创建账号，不开放陌生人注册。</p></div>
        <div className="account-create"><input value={newUser.username} onChange={e => setNewUser({...newUser, username: e.target.value})} placeholder="朋友用户名"/><input type="password" value={newUser.password} onChange={e => setNewUser({...newUser, password: e.target.value})} placeholder="初始密码（至少 12 位）"/><button type="button" className="outline" disabled={busy || newUser.username.trim().length < 3 || newUser.password.length < 12} onClick={createAccount}>创建账号</button></div>
        <div className="user-list">{users.map(item => <div key={item.id}><span>{item.username}</span><small>{item.role === 'admin' ? '管理员' : '普通用户'}</small></div>)}</div>
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
  const [page, setPage] = useState('home')
  const [tasks, setTasks] = useState([])
  const [selected, setSelected] = useState(null)
  const refresh = useCallback(async () => { const items = await api.tasks(); setTasks(items); return items }, [])
  const removeTask = useCallback(async (taskId) => {
    await api.deleteTask(taskId)
    setTasks(current => current.filter(task => task.id !== taskId))
    if (selected === taskId) { setSelected(null); setPage('history') }
  }, [selected])
  useEffect(() => { api.me().then(async me => { setUser(me); await refresh() }).catch(() => setUser(null)) }, [refresh])
  useEffect(() => {
    if (!user || !tasks.some(t => !['completed','failed'].includes(t.status))) return
    const timer = setInterval(() => refresh().catch(console.error), 2200); return () => clearInterval(timer)
  }, [user, tasks, refresh])
  if (user === undefined) return <main className="loading-page"><LoaderCircle className="spin"/>加载中</main>
  if (!user) return <Login onLogin={async me => { setUser(me); await refresh() }}/>
  const open = id => { setSelected(id); setPage('detail') }
  return <div className="app"><Header page={page} setPage={setPage} user={user} onLogout={async () => { await api.logout(); setUser(null) }}/>
    {page === 'home' && <Home tasks={tasks} refresh={refresh} onOpen={open}/>} 
    {page === 'history' && <main className="shell history-page"><div className="history-heading"><History/><div><h1>历史记录</h1><p>你的听写、亮点与改编结果都保存在这里。</p></div></div><TaskTable tasks={tasks} onOpen={open} onDelete={removeTask} full/></main>}
    {page === 'settings' && <SettingsPage user={user} onBack={() => setPage('home')}/>}
    {page === 'detail' && selected && <Detail taskId={selected} onBack={() => { refresh(); setPage('home') }} onSettings={() => setPage('settings')}/>} 
    <footer className="statusbar"><span><span className="footer-wave"><i/><i/><i/></span><i className="online"/>ASR 服务在线</span><span><LockKeyhole size={15}/>仅你可访问</span></footer>
  </div>
}

function clock(seconds = 0) { const s = Math.max(0, Math.floor(seconds)); return `${String(Math.floor(s / 3600)).padStart(2,'0')}:${String(Math.floor((s % 3600) / 60)).padStart(2,'0')}:${String(s % 60).padStart(2,'0')}` }
function friendlyDate(value) { if (!value) return '—'; const d = new Date(value); const today = new Date(); return d.toDateString() === today.toDateString() ? `今天 ${d.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit'})}` : d.toLocaleDateString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}) }
function sourceDate(value) { if (!value) return '未知日期'; const d = new Date(value); return d.toLocaleDateString('zh-CN',{year:'numeric',month:'2-digit',day:'2-digit'}).replace(/\//g, '-') }
function fileSize(bytes) { if (bytes < 1024**2) return `${(bytes/1024).toFixed(1)} KB`; return `${(bytes/1024**2).toFixed(1)} MB` }

export default App
