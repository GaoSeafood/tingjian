import { useState } from 'react'
import { Pause, Play, RotateCcw, RotateCw } from 'lucide-react'

const bars = [8, 14, 21, 12, 30, 19, 39, 26, 46, 32, 54, 28, 40, 19, 34, 26, 17, 29, 13, 21, 10, 17, 9, 14, 23, 12, 19, 8, 14, 9, 12, 6]
const time = value => `${Math.floor(value / 60).toString().padStart(2, '0')}:${Math.floor(value % 60).toString().padStart(2, '0')}`

export default function AudioPlayer({ src, mediaRef, onError }) {
  const [playing, setPlaying] = useState(false)
  const [current, setCurrent] = useState(0)
  const [duration, setDuration] = useState(0)
  const [rate, setRate] = useState(1)
  const [error, setError] = useState('')
  const seek = value => { if (mediaRef.current && duration) mediaRef.current.currentTime = Math.min(duration, Math.max(0, value)) }
  const toggle = async () => {
    const audio = mediaRef.current
    if (!audio) return
    if (!audio.paused) audio.pause()
    else try { await audio.play(); setError('') } catch { setError('音频暂时无法播放，请稍后重试。') }
  }
  return <div className="miji-audio-player">
    <audio ref={mediaRef} src={src} preload="metadata" onLoadedMetadata={event => setDuration(Number.isFinite(event.currentTarget.duration) ? event.currentTarget.duration : 0)} onTimeUpdate={event => setCurrent(event.currentTarget.currentTime)} onPlay={() => setPlaying(true)} onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)} onError={() => { setError('音频暂时无法播放，请稍后重试。'); onError?.() }}/>
    <div className="audio-brand-wave" aria-hidden="true">{bars.map((height, index) => <i key={index} className={duration && index / bars.length <= current / duration ? 'played' : ''} style={{ height: `${height}px` }}/>)}</div>
    <input className="audio-seek" type="range" min="0" max={duration || 1} step="0.1" value={Math.min(current, duration || 0)} disabled={!duration} onChange={event => seek(Number(event.target.value))} aria-label="音频播放进度"/>
    <div className="audio-time"><span>{time(current)} / {time(duration)}</span></div>
    <div className="audio-transport"><label><span className="sr-only">播放速度</span><select value={rate} onChange={event => { const next = Number(event.target.value); setRate(next); if (mediaRef.current) mediaRef.current.playbackRate = next }}><option value="0.75">0.75×</option><option value="1">1×</option><option value="1.25">1.25×</option><option value="1.5">1.5×</option><option value="2">2×</option></select></label><button type="button" onClick={() => seek(current - 15)} disabled={!duration} aria-label="后退 15 秒"><RotateCcw size={23}/><small>15</small></button><button type="button" className="audio-play" aria-label={playing ? '暂停音频' : '播放音频'} onClick={toggle}>{playing ? <Pause size={23} fill="currentColor"/> : <Play size={23} fill="currentColor"/>}</button><button type="button" onClick={() => seek(current + 15)} disabled={!duration} aria-label="前进 15 秒"><RotateCw size={23}/><small>15</small></button></div>
    {error && <p className="audio-error" role="alert">{error}</p>}
  </div>
}
