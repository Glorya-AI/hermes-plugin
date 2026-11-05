"""Plain-text messages the plugin posts into chats (every Hermes surface renders plain text)."""

from __future__ import annotations

import time
from typing import Any, Iterable, Optional

KIND_LABEL = {
    "image_ad": "Image ad",
    "video_ad": "Video ad",
    "landing_page": "Landing page",
    "website": "Website",
    "campaign": "Ad campaign",
}
KIND_ICON = {"image_ad": "🖼", "video_ad": "🎬", "landing_page": "🧩", "website": "🌐", "campaign": "📣"}
PLATFORM_LABEL = {"meta": "Meta", "google_ads": "Google Ads", "tiktok": "TikTok"}


def clip(value: Any, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def label(kind: str) -> str:
    return KIND_LABEL.get(kind, "Glorya job")


def _elapsed(since: float, now: Optional[float] = None) -> str:
    seconds = max(0, int((now or time.time()) - since))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    return f"{minutes} min" if minutes < 60 else f"{minutes // 60} h {minutes % 60:02d} min"


def headline(kind: str, title: str = "") -> str:
    name = clip(title, 60)
    return f"{KIND_ICON.get(kind, '✨')} Glorya · {label(kind)}" + (f" · {name}" if name else "")


def started(kind: str, title: str, open_url: str) -> str:
    lines = [headline(kind, title), "Started. I'll update this message and post the result here."]
    if open_url:
        lines.append(f"Open in Glorya: {open_url}")
    return "\n".join(lines)


def status(view: dict[str, Any], started_at: float, now: Optional[float] = None) -> str:
    """The live progress message, edited in place while the job runs."""
    kind, state = str(view.get("kind") or ""), str(view.get("status") or "running")
    lines = [headline(kind, str(view.get("title") or ""))]
    if state == "running":
        site = view.get("site") if isinstance(view.get("site"), dict) else None
        detail = clip(view.get("progress"), 220) or (f"Building: {site.get('status')}" if site else "Working…")
        lines.append(f"⏳ {detail} · {_elapsed(started_at, now)}")
    elif state == "needs_input":
        lines.append("✋ Glorya needs a decision. See the question below.")
    elif state == "completed":
        lines.append(f"✅ Done in {_elapsed(started_at, now)}.")
    elif state == "failed":
        lines.append("❌ " + (clip(view.get("error") or view.get("progress"), 220) or "Glorya couldn't finish this job."))
    elif state == "cancelled":
        lines.append("⏹ Stopped. Finished files stay in Glorya.")
    if view.get("open_url"):
        lines.append(f"Open in Glorya: {view['open_url']}")
    return "\n".join(lines)


def question(view: dict[str, Any], q: dict[str, Any], job_ref: str) -> str:
    kind = str(view.get("kind") or "")
    lines = [f"✋ Glorya · {label(kind)} needs your answer", clip(q.get("question"), 600)]
    details = clip(q.get("details"), 400)
    if details:
        lines.append(details)
    choices = [str(c) for c in q.get("choices") or []]
    if choices:
        lines.extend(f"  {index}. {choice}" for index, choice in enumerate(choices, 1))
        lines.append(f"Reply with your choice, or tap /glorya answer {job_ref}.")
    else:
        lines.append(f"Reply in your own words, or send /glorya answer {job_ref} <your answer>.")
    for url in [str(u) for u in q.get("preview_images") or []][:4]:
        lines.append(f"Preview: {url}")
    return "\n".join(lines)


def result_links(view: dict[str, Any]) -> str:
    """Final message with links, for chats that don't take attachments (or when files are too big)."""
    kind = str(view.get("kind") or "")
    lines = [f"✅ {headline(kind, str(view.get('title') or ''))} is ready."]
    progress = clip(view.get("progress"), 700)
    if progress:
        lines.append(progress)
    for asset in assets_of(view):
        lines.append(f"{asset.get('label') or asset.get('type') or 'File'}: {asset.get('url')}")
    campaign = view.get("campaign") if isinstance(view.get("campaign"), dict) else None
    if campaign:
        lines.append(campaign_line(campaign))
        if campaign.get("manage_url"):
            lines.append(f"Manage: {campaign['manage_url']}")
        lines.append("Live status, spend and results: /glorya campaigns")
    site = view.get("site") if isinstance(view.get("site"), dict) else None
    if site:
        if site.get("live_url"):
            lines.append(f"Live: {site['live_url']}")
        if site.get("preview_url"):
            lines.append(f"Preview: {site['preview_url']}")
        if not site.get("live_url"):
            lines.append("Not live yet. Say \"publish it\" or send /glorya publish when you want it online.")
    if view.get("open_url"):
        lines.append(f"Open in Glorya: {view['open_url']}")
    return "\n".join(lines)


def delivery_turn(view: dict[str, Any], files: Iterable[dict[str, Any]]) -> str:
    """The message the plugin injects so the agent posts the finished files as attachments."""
    kind = str(view.get("kind") or "")
    media = "\n".join(f"MEDIA:{f['path']}" for f in files)
    copy = clip(view.get("progress"), 900)
    return (
        f"[Glorya plugin] The {label(kind).lower()} job {view.get('job_id')} you started is finished. "
        "Send the result to the user now: one or two short sentences about what is attached"
        + (" (use the ad copy below if it fits)" if copy else "")
        + ", then these attachment lines exactly as written, each on its own line, then the Glorya link. "
        "Don't call any tool.\n\n"
        + (f"Ad copy from Glorya: {copy}\n\n" if copy else "")
        + f"{media}\n\nGlorya link: {view.get('open_url') or ''}"
    )


def campaign_line(campaign: dict[str, Any]) -> str:
    platform = PLATFORM_LABEL.get(str(campaign.get("platform") or ""), "Campaign")
    budget = campaign.get("daily_budget")
    money = f" · {budget} {campaign.get('currency') or ''}/day".rstrip() if budget else ""
    name = clip(campaign.get("name"), 60)
    # list_campaigns rows carry the live status; get_job's campaign carries the draft stage.
    state = campaign.get("status") or campaign.get("stage") or "unknown"
    return f"{platform}{f' · {name}' if name else ''} · {state}{money}"


def money(value: Any, currency: Any) -> str:
    try:
        amount = f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "-"
    return f"{amount} {currency or ''}".strip()


def assets_of(view: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in view.get("assets") or [] if isinstance(a, dict) and str(a.get("url") or "").startswith("https://")]


def job_line(job: Any, now: Optional[float] = None) -> str:
    icon = {"completed": "✅", "failed": "❌", "cancelled": "⏹", "needs_input": "✋"}.get(job.status, "⏳")
    title = clip(job.title, 48) or label(job.kind)
    return f"{icon} {job.short_id} · {label(job.kind)} · {title} · {job.status} · {_elapsed(job.updated_at, now)} ago"


def failure(error: Any) -> str:
    message = getattr(error, "message", None) or str(error)
    link = error.link() if hasattr(error, "link") else None
    return f"Glorya: {message}" + (f"\n{link}" if link else "")
