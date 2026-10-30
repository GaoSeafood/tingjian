import { useLayoutEffect, useRef } from 'react'

function Segment({ segment, index, disabled, onEdit, onSeek }) {
  const ref = useRef(null)
  useLayoutEffect(() => {
    const area = ref.current
    const resize = () => {
      area.style.height = 'auto'
      area.style.height = `${area.scrollHeight}px`
    }
    resize()
    let width = area.clientWidth
    const observer = new ResizeObserver(() => {
      if (width === area.clientWidth) return
      width = area.clientWidth
      resize()
    })
    observer.observe(area)
    return () => observer.disconnect()
  }, [segment.text])
  return <section className="transcript-paragraph">
    <div className="transcript-paragraph-meta"><button type="button" onClick={() => onSeek(segment.start_seconds ?? segment.start)} aria-label={`播放 ${segment.start || '00:00'}`}><span>[{segment.start || '00:00'}]</span></button>{segment.speaker && <span>{segment.speaker}</span>}</div>
    <textarea ref={ref} aria-label={`编辑第 ${index + 1} 段听写稿`} value={segment.text} disabled={disabled} onChange={event => onEdit(event.target.value)} rows={2} spellCheck="false" />
  </section>
}

export default function TranscriptDocument({ segments, disabled, onChange, onSeek }) {
  return <div className="miji-transcript-document">{segments.length ? segments.map((segment, index) => <Segment key={segment._index ?? index} segment={segment} index={index} disabled={disabled} onSeek={onSeek} onEdit={text => onChange(segments.map((item, current) => current === index ? {...item, text} : item))}/>) : <p className="document-empty">没有匹配的文稿内容。</p>}</div>
}
