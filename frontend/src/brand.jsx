import { useEffect, useRef } from 'react'
import { ArrowRight, CircleHelp, X } from 'lucide-react'

export function BrandLogo() {
  return <span className="brand-lockup"><img className="brand-wordmark" src="/brand/miji-logo.png" alt="米叽 MIJI" width="1000" height="333" /><img className="brand-mark" src="/brand/miji-mark.png" alt="米叽" width="1254" height="1254" /></span>
}

export function HelpDialog({ open, onClose, lang = 'zh' }) {
  const ref = useRef(null)
  const en = lang === 'en'
  useEffect(() => {
    if (open && !ref.current.open) ref.current.showModal()
    else if (!open && ref.current.open) ref.current.close()
  }, [open])
  return <dialog ref={ref} className="miji-help" onClose={onClose} onClick={event => { if (event.target === event.currentTarget) onClose() }} aria-labelledby="help-title">
    <button className="help-close" aria-label={en ? 'Close help' : '关闭帮助'} onClick={onClose}><X size={20}/></button>
    <CircleHelp size={28}/><h2 id="help-title">{en ? 'A little help getting started' : '好内容，从这里开始。'}</h2>
    <ol>
      <li><b>{en ? 'Add your media' : '添加素材'}</b><p>{en ? 'Upload an audio or video file, or paste a public video link.' : '直接粘贴公开视频链接，也可以选择或拖入音视频文件。'}</p></li>
      <li><b>{en ? 'Review your transcript' : '听写，然后整理'}</b><p>{en ? 'Edit the transcript, jump to timestamps, copy it, or export TXT and SRT.' : '听写完成后可以编辑原文、定位时间点、复制全文，或导出 TXT 和 SRT。'}</p></li>
      <li><b>{en ? 'Choose your next step' : '按需要，继续创作'}</b><p>{en ? 'Find highlights, analyze video frames, or rewrite when you choose. Use Video downloads to save source videos separately.' : '主动选择找亮点、画面分析或复刻改编。只想保存视频时，使用独立的「视频下载」入口。'}</p></li>
    </ol>
    <p className="help-note">{en ? 'Source media is temporary and is removed according to the retention policy. Contact your administrator for account or service support.' : '原始媒体会按保留策略自动清理。遇到账号或服务问题，请联系管理员。'}</p>
    <button className="primary" onClick={onClose}>{en ? 'Got it' : '知道啦'}<ArrowRight size={17}/></button>
  </dialog>
}

export function ToolChoice({ icon: Icon, title, description, label, onClick, disabled, active, note }) {
  return <section className={`miji-tool ${active ? 'is-active' : ''} ${disabled ? 'is-disabled' : ''}`}>
    <div className="miji-tool-heading"><span><Icon size={23} strokeWidth={1.7}/></span><div><h3>{title}</h3><p>{description}</p></div></div>
    {note && <small>{note}</small>}
    <button type="button" className="primary" onClick={onClick} disabled={disabled}>{label}<ArrowRight size={17}/></button>
  </section>
}
