/**
 * Glorya Studio for Hermes Desktop.
 *
 * - "Glorya: open studio" (⌘K) opens a workspace tab with every Glorya job this profile follows: live
 *   progress, finished videos and images, Glorya's open questions as buttons, and quick actions.
 * - A status-bar chip shows running jobs and jobs waiting for an answer.
 * - `::glorya-job{id="…"}` in an assistant reply renders that job as a live card in the chat.
 *
 * Data comes from this plugin's backend (dashboard/plugin_api.py) through ctx.rest. Every action is a
 * `/glorya …` message sent to the job's chat, so it runs with the user's Glorya sign-in and approvals.
 */

import * as sdk from '@hermes/plugin-sdk'
import { host, PALETTE_AREA, STATUSBAR_AREAS, TRANSCRIPT_DIRECTIVE_AREA } from '@hermes/plugin-sdk'
import { useEffect, useRef, useState } from 'react'
import { jsx, jsxs } from 'react/jsx-runtime'

const PLUGIN_ID = 'glorya'
const WORKSPACE_ID = 'glorya-studio'
const JOB_ID = /^[A-Za-z0-9_-]{6,200}$/
const KIND = {
  image_ad: ['🖼', 'Image ad'],
  video_ad: ['🎬', 'Video ad'],
  landing_page: ['🧩', 'Landing page'],
  website: ['🌐', 'Website']
}
const STATUS = {
  running: ['Working', 'var(--ui-accent)'],
  needs_input: ['Needs your answer', 'var(--ui-accent)'],
  completed: ['Done', 'var(--ui-text-secondary)'],
  failed: ['Failed', 'var(--ui-text-secondary)'],
  cancelled: ['Stopped', 'var(--ui-text-tertiary)']
}

// One counter for "something changed": bumped by backend events; every view refetches on a bump.
let version = 0
const listeners = new Set()
const bump = () => {
  version += 1
  listeners.forEach(fn => fn(version))
}

function useVersion() {
  const [v, setV] = useState(version)
  useEffect(() => {
    listeners.add(setV)
    return () => listeners.delete(setV)
  }, [])
  return v
}

function useRest(ctx, path, { pollWhile } = {}) {
  const v = useVersion()
  const [state, setState] = useState({ data: null, error: null })
  const latest = useRef(null)
  useEffect(() => {
    let alive = true
    const load = () =>
      ctx.rest(path).then(
        data => {
          latest.current = data
          if (alive) setState({ data, error: null })
        },
        error => alive && setState(s => ({ data: s.data, error: String(error?.message || error) }))
      )
    load()
    // Events drive updates; a slow poll covers a Desktop connected while the gateway was busy.
    const timer = setInterval(() => {
      if (!pollWhile || pollWhile(latest.current)) load()
    }, 20000)
    return () => {
      alive = false
      clearInterval(timer)
    }
  }, [path, v])
  return state
}

const short = id => String(id || '').slice(0, 8)

async function sendTo(sessionId, text, { insert = false } = {}) {
  const composer = host.composer
  if (!composer) return false
  const send = id =>
    insert && typeof composer.insertText === 'function'
      ? composer.insertText(id, text, { mode: 'block' })
      : Promise.resolve(composer.submit(id, text))
  if (sessionId) {
    if (await send(sessionId)) return true
    if (typeof host.openSession === 'function') {
      try {
        await host.openSession(sessionId)
        for (let i = 0; i < 20; i += 1) {
          if (await send(sessionId)) return true
          await new Promise(resolve => setTimeout(resolve, 150))
        }
      } catch {
        // fall through to the active composer
      }
    }
  }
  return send(null)
}

function act(sessionId, text, insert) {
  sendTo(sessionId, text, { insert }).then(ok => {
    if (!ok) host.notify({ kind: 'warning', message: 'Open a chat to send this to Glorya.' })
  })
}

const box = {
  border: '1px solid var(--ui-stroke-secondary)',
  borderRadius: 10,
  padding: 12,
  display: 'flex',
  flexDirection: 'column',
  gap: 8
}
const muted = { color: 'var(--ui-text-tertiary)', fontSize: 12 }

function Button({ children, onClick, primary }) {
  return jsx(sdk.Button, { size: 'sm', variant: primary ? 'default' : 'outline', onClick, children })
}

function Media({ asset }) {
  const [broken, setBroken] = useState(false)
  if (broken) {
    return jsx('a', { href: asset.url, target: '_blank', rel: 'noreferrer', style: muted, children: asset.label || 'Open file' })
  }
  const style = { width: '100%', borderRadius: 8, background: 'var(--ui-stroke-secondary)' }
  if (asset.type === 'video') {
    return jsx('video', {
      src: asset.url,
      poster: asset.poster_url || undefined,
      controls: true,
      preload: 'metadata',
      playsInline: true,
      style,
      onError: () => setBroken(true)
    })
  }
  return jsx('img', { src: asset.preview_url || asset.url, alt: asset.label || 'Glorya image', style, onError: () => setBroken(true) })
}

function Questions({ job, sessionId }) {
  return (job.questions || []).map(q =>
    jsxs(
      'div',
      {
        style: { ...box, borderColor: 'var(--ui-accent)' },
        children: [
          jsx('div', { style: { fontWeight: 600 }, children: q.question }),
          q.details ? jsx('div', { style: muted, children: q.details }) : null,
          jsx('div', {
            style: { display: 'flex', flexWrap: 'wrap', gap: 6 },
            children: (q.choices || []).length
              ? q.choices.map(choice =>
                  jsx(Button, { onClick: () => act(sessionId, `/glorya answer ${short(job.job_id)} ${choice}`), children: choice }, choice)
                )
              : jsx(Button, { onClick: () => act(sessionId, `/glorya answer ${short(job.job_id)} `, true), children: 'Answer…' })
          })
        ]
      },
      q.request_id
    )
  )
}

function JobCard({ ctx, job, sessionId }) {
  const [icon, kind] = KIND[job.kind] || ['✨', 'Glorya job']
  const [label, color] = STATUS[job.status] || [job.status, 'var(--ui-text-secondary)']
  const target = sessionId ?? job.session_id ?? null
  const site = job.site || null
  const assets = (job.assets || []).slice(0, 4)
  const isAd = job.kind === 'image_ad' || job.kind === 'video_ad'
  return jsxs('div', {
    style: box,
    children: [
      jsxs('div', {
        style: { display: 'flex', alignItems: 'center', gap: 8 },
        children: [
          jsx('span', { children: icon }),
          jsx('span', { style: { fontWeight: 600, flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }, children: job.title || kind }),
          jsxs('span', {
            style: { fontSize: 12, color },
            children: [job.status === 'running' ? jsx(sdk.Codicon, { name: 'loading', size: 12, spinning: true }) : null, ' ', label]
          })
        ]
      }),
      jsx('div', { style: muted, children: `${kind} · ${short(job.job_id)}` }),
      job.progress && job.status !== 'completed' ? jsx('div', { style: { fontSize: 13 }, children: job.progress }) : null,
      jsx(Questions, { job, sessionId: target }),
      assets.length
        ? jsx('div', {
            style: { display: 'grid', gridTemplateColumns: assets.length > 1 ? '1fr 1fr' : '1fr', gap: 8 },
            children: assets.map(asset => jsx(Media, { asset }, asset.id || asset.url))
          })
        : null,
      job.status === 'completed' && job.progress ? jsx('div', { style: { fontSize: 13, whiteSpace: 'pre-wrap' }, children: job.progress }) : null,
      jsxs('div', {
        style: { display: 'flex', flexWrap: 'wrap', gap: 6 },
        children: [
          job.open_url ? jsx(Button, { onClick: () => ctx.os.openExternal(job.open_url), children: 'Open in Glorya' }) : null,
          site?.live_url ? jsx(Button, { onClick: () => ctx.os.openExternal(site.live_url), children: 'Open live site' }) : null,
          site?.preview_url && !site?.live_url ? jsx(Button, { onClick: () => ctx.os.openExternal(site.preview_url), children: 'Preview' }) : null,
          site && job.status === 'completed' && !site.live_url
            ? jsx(Button, { primary: true, onClick: () => act(target, `/glorya publish ${short(job.job_id)}`), children: 'Publish…' })
            : null,
          job.status === 'completed' || job.status === 'failed'
            ? jsx(Button, { onClick: () => act(target, `/glorya refine ${short(job.job_id)} `, true), children: 'Change…' })
            : null,
          job.status === 'running' && isAd ? jsx(Button, { onClick: () => act(target, `/glorya cancel ${short(job.job_id)}`), children: 'Stop' }) : null
        ]
      })
    ]
  })
}

const active = data => Boolean(data && (data.running || data.waiting))

function Studio({ ctx }) {
  const { data, error } = useRest(ctx, 'jobs?limit=30', { pollWhile: active })
  const jobs = data?.jobs || []
  return jsxs('div', {
    style: { padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', height: '100%' },
    children: [
      jsxs('div', {
        style: { display: 'flex', alignItems: 'baseline', gap: 8 },
        children: [
          jsx('div', { style: { fontSize: 16, fontWeight: 600 }, children: 'Glorya Studio' }),
          jsx('div', { style: muted, children: data ? `${data.running} running · ${data.waiting} waiting` : 'Loading…' })
        ]
      }),
      error ? jsx('div', { style: muted, children: `Couldn't load jobs: ${error}` }) : null,
      !jobs.length && data
        ? jsxs('div', {
            style: { ...box, alignItems: 'flex-start' },
            children: [
              jsx('div', { style: { fontWeight: 600 }, children: 'No Glorya jobs yet' }),
              jsx('div', { style: muted, children: 'Ask Hermes for an image ad, a video ad, a landing page or a website, or type /glorya image <brief>.' })
            ]
          })
        : null,
      ...jobs.map(job => jsx(JobCard, { ctx, job }, job.job_id))
    ]
  })
}

function Chip({ ctx, open }) {
  const { data } = useRest(ctx, 'jobs?limit=20', { pollWhile: active })
  if (!active(data)) return null
  const parts = [data.running ? `${data.running} running` : null, data.waiting ? `${data.waiting} waiting` : null].filter(Boolean)
  return jsx('button', {
    onClick: open,
    title: 'Open Glorya Studio',
    style: { fontSize: 12, color: 'var(--ui-text-secondary)', background: 'none', border: 'none', cursor: 'pointer' },
    children: `✦ Glorya · ${parts.join(' · ')}`
  })
}

function JobDirective({ ctx, id, sessionId }) {
  const { data, error } = useRest(ctx, `job?id=${encodeURIComponent(id)}`, { pollWhile: d => d?.job && !['completed', 'failed', 'cancelled'].includes(d.job.status) })
  if (error && !data) return jsx('div', { style: muted, children: `Glorya job ${short(id)}` })
  if (!data?.job) return jsx('div', { style: muted, children: 'Loading Glorya job…' })
  return jsx(JobCard, { ctx, job: data.job, sessionId })
}

const plugin = {
  id: PLUGIN_ID,
  name: 'Glorya',
  description: 'Glorya Studio: follow your Glorya ads and pages, answer questions and watch results in Hermes Desktop.',
  register(ctx) {
    let close = null
    const open = () => {
      if (typeof host.openWorkspace !== 'function') {
        host.notify({ kind: 'warning', message: 'Update Hermes Desktop to open Glorya Studio.' })
        return
      }
      close = host.openWorkspace(WORKSPACE_ID, {
        title: 'Glorya Studio',
        minWidth: '24rem',
        onClose: () => {
          close = null
        },
        render: () => jsx(Studio, { ctx })
      })
    }
    ctx.onEvent(`plugin.${PLUGIN_ID}.job.updated`, bump)
    ctx.onEvent('tool.complete', event => {
      const name = String(event?.payload?.name || '')
      if (name.startsWith('mcp__glorya__') || name.startsWith('glorya_')) bump()
    })
    ctx.onDispose(() => {
      close?.()
      listeners.clear()
    })
    ctx.registerMany([
      {
        id: 'open-studio',
        area: PALETTE_AREA,
        data: { id: 'glorya.studio', label: 'Glorya: open studio', keywords: ['glorya', 'ads', 'video', 'image', 'landing page', 'website', 'jobs'], run: open }
      },
      {
        id: 'open-settings',
        area: PALETTE_AREA,
        data: { id: 'glorya.settings', label: 'Glorya: settings', keywords: ['glorya', 'settings'], run: () => host.navigate(`/settings?tab=plugins&agent=${PLUGIN_ID}`) }
      },
      { id: 'chip', area: STATUSBAR_AREAS.right, order: 70, render: () => jsx(Chip, { ctx, open }) },
      {
        id: 'job-card',
        area: TRANSCRIPT_DIRECTIVE_AREA,
        data: {
          name: 'glorya-job',
          render: ({ attrs, sessionId }) => (JOB_ID.test(attrs?.id || '') ? jsx(JobDirective, { ctx, id: attrs.id, sessionId }) : null)
        }
      }
    ])
  }
}

export default plugin
