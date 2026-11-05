"""``/glorya`` — start and steer Glorya jobs from any chat without spending model tokens."""

from __future__ import annotations

import shlex
from typing import Any, Optional

from . import render
from .client import GloryaError
from .store import Job

USAGE = """Glorya — on-brand ads and pages, followed right here.
  /glorya image <brief>          start an image ad
  /glorya video <brief>          start a video ad (add --format ugc, --review)
  /glorya page <brief>           start a landing page
  /glorya site <brief>           start a website
  /glorya campaign <brief>       build and launch an ad campaign (--platform meta|google_ads|tiktok, --budget 30, --review)
  /glorya credits                credits left and your plan
  /glorya campaigns | sites      your campaigns with spend, your pages and sites
  /glorya jobs                   jobs in this chat
  /glorya status [job]           a job's state
  /glorya answer [job] [answer]  answer Glorya's open question
  /glorya refine [job] <change>  change a result
  /glorya publish [job] [slug]   put a landing page or website live
  /glorya cancel [job]           stop an image or video ad
  /glorya follow <job>           follow a job here
  /glorya brand | formats        your brand, the video styles
[job] is the 8-character id from /glorya jobs; it defaults to this chat's latest job."""

CREATE_ALIASES = {
    "image": "image_ad", "img": "image_ad", "video": "video_ad", "vid": "video_ad",
    "page": "landing_page", "landing": "landing_page", "site": "website", "website": "website",
    "campaign": "campaign",
}


def _split(raw: str) -> tuple[str, str]:
    raw = (raw or "").strip()
    head, _, rest = raw.partition(" ")
    return head.lower(), rest.strip()


def _flags(text: str) -> tuple[dict[str, Any], str]:
    """Pull ``--review`` and ``--format <id>`` out of a brief."""
    options: dict[str, Any] = {}
    try:
        words = shlex.split(text)
    except ValueError:
        words = text.split()
    kept: list[str] = []
    skip = False
    for index, word in enumerate(words):
        if skip:
            skip = False
            continue
        if word == "--review":
            options["review"] = True
        elif word == "--format" and index + 1 < len(words):
            options["format"] = words[index + 1].strip().lower().replace("-", "_")
            skip = True
        elif word.startswith("--format="):
            options["format"] = word.split("=", 1)[1].strip().lower().replace("-", "_")
        elif word in ("--platform", "--budget") and index + 1 < len(words):
            options[word[2:]] = words[index + 1].strip().lower()
            skip = True
        else:
            kept.append(word)
    return options, " ".join(kept).strip()


class Commands:
    def __init__(self, plugin: Any):
        self.plugin = plugin

    def __call__(self, raw_args: str = "", *, session_key: str = "", **_: Any) -> str:
        try:
            return self.dispatch(raw_args, session_key)
        except GloryaError as error:
            return render.failure(error)
        except Exception as exc:  # a slash command must always answer
            return f"Glorya: something went wrong ({type(exc).__name__}). Try again, or open https://platform.glorya.ai"

    def dispatch(self, raw_args: str, session_key: str) -> str:
        self.plugin.housekeep()
        verb, rest = _split(raw_args)
        if verb in ("", "help", "-h", "--help"):
            return self.help(session_key)
        if verb in CREATE_ALIASES:
            return self.create(CREATE_ALIASES[verb], rest)
        handler = getattr(self, f"cmd_{verb}", None)
        if handler is None:
            return f"Unknown /glorya command '{verb}'.\n\n{USAGE}"
        return handler(rest, session_key)

    # -- helpers --------------------------------------------------------------------------------

    def _job(self, ref: str, session_key: str) -> Job:
        job = self.plugin.store.find(ref, session_key=session_key)
        if job is None:
            raise GloryaError("job_not_found", "No matching Glorya job here. Send /glorya jobs to see them."
                              if ref else "No Glorya job in this chat yet. Start one with /glorya image <brief>.")
        return job

    def _job_and_text(self, rest: str, session_key: str) -> tuple[Job, str]:
        """``[job] text``: the first word is a job id when it matches one, else part of the text."""
        head, _, tail = rest.partition(" ")
        if head and len(head) >= 6:
            job = self.plugin.store.find(head, session_key=session_key)
            if job is not None:
                return job, tail.strip()
        return self._job("", session_key), rest.strip()

    def _follow(self, ref: dict[str, Any], kind: str, title: str = "") -> str:
        """Follow the job here; returns a hint for chats where the plugin can't post updates."""
        job_id = str(ref.get("job_id") or "")
        if self.plugin.follower.start(job_id, kind=str(ref.get("kind") or kind), title=title,
                                      open_url=str(ref.get("open_url") or ""), source="command"):
            return " Updates follow in this chat."
        return f" Check it with /glorya status {job_id[:8]}, or open {ref.get('open_url') or 'Glorya'}."

    # -- commands -------------------------------------------------------------------------------

    def help(self, session_key: str) -> str:
        jobs = self.plugin.store.recent(session_key=session_key, limit=5) if session_key else []
        if not jobs:
            return USAGE
        return USAGE + "\n\nIn this chat:\n" + "\n".join(render.job_line(j) for j in jobs)

    def create(self, kind: str, rest: str) -> str:
        options, brief = _flags(rest)
        if not brief:
            return f"Tell Glorya what to make, e.g. /glorya {kind.split('_')[0]} summer sale for our new serum"
        if kind != "video_ad":
            options.pop("format", None)
        if kind in ("landing_page", "website"):
            options.pop("review", None)
        platform, budget = options.pop("platform", None), options.pop("budget", None)
        if kind == "campaign":
            if platform:
                options["platform"] = platform.replace("-", "_")
            if budget:
                if not budget.isdigit():
                    return "The budget is a whole number per day, e.g. --budget 30"
                options["daily_budget"] = int(budget)
        ref = self.plugin.glorya().create(kind, brief[:4000], **options)
        if not self.plugin.store.get(str(ref.get("job_id") or "")):
            self.plugin.store.track(str(ref.get("job_id")), kind=kind, title=render.clip(brief, 60),
                                    open_url=str(ref.get("open_url") or ""), source="command")
        return f"{render.headline(kind)} started.{self._follow(ref, kind, title=render.clip(brief, 60))}"

    def cmd_jobs(self, rest: str, session_key: str) -> str:
        everywhere = rest.strip().lower() == "all"
        jobs = self.plugin.store.recent(session_key="" if everywhere else session_key, limit=10)
        if not jobs:
            return "No Glorya jobs yet." + ("" if everywhere else " Send /glorya jobs all for every chat.")
        return "\n".join(render.job_line(j) for j in jobs)

    def cmd_status(self, rest: str, session_key: str) -> str:
        job = self._job(rest.strip(), session_key)
        view = self.plugin.glorya().get_job(job.job_id)
        self.plugin.store.save_view(job.job_id, {**view, "job_id": job.job_id})
        text = render.status(view, job.created_at, self.plugin.clock())
        if view.get("status") == "completed":
            text = render.result_links(view)
        for q in view.get("questions") or []:
            text += "\n\n" + render.question(view, q, job.short_id)
        return text

    def cmd_answer(self, rest: str, session_key: str) -> str:
        job, answer = self._job_and_text(rest, session_key)
        view = self.plugin.glorya().get_job(job.job_id)
        questions = [q for q in view.get("questions") or [] if isinstance(q, dict)]
        if view.get("status") != "needs_input" or not questions:
            return f"Glorya has no open question on {job.short_id} ({view.get('status')})."
        q = questions[0]
        choices = [str(c) for c in q.get("choices") or []]
        if not answer and choices:
            picked: Optional[str] = self.plugin.ctx.ask_choice(render.clip(q.get("question"), 300), choices)
            if not picked:
                return render.question(view, q, job.short_id)
            answer = picked
        elif not answer:
            return f"Send your answer: /glorya answer {job.short_id} <your words>"
        if choices and answer.isdigit() and 1 <= int(answer) <= len(choices):
            answer = choices[int(answer) - 1]
        self.plugin.glorya().respond(job.job_id, answer[:4000], request_id=q.get("request_id"))
        note = self._follow({"job_id": job.job_id, "kind": job.kind, "open_url": job.open_url}, job.kind, job.title)
        return f"Sent \"{render.clip(answer, 80)}\" to Glorya.{note}"

    def cmd_refine(self, rest: str, session_key: str) -> str:
        job, instruction = self._job_and_text(rest, session_key)
        if not instruction:
            return f"What should change? /glorya refine {job.short_id} make the headline shorter"
        ref = self.plugin.glorya().refine(job.job_id, instruction[:4000])
        note = self._follow(ref, job.kind, job.title)
        return f"Asked Glorya to change {job.short_id}: \"{render.clip(instruction, 80)}\".{note}"

    def cmd_publish(self, rest: str, session_key: str) -> str:
        job, slug = self._job_and_text(rest, session_key)
        if job.kind not in ("landing_page", "website"):
            return f"{job.short_id} is a {render.label(job.kind).lower()}; only landing pages and websites can be published."
        picked = self.plugin.ctx.ask_choice(f"Put {render.clip(job.title, 60) or job.short_id} live on the internet?",
                                            [{"value": "yes", "label": "Publish"}, {"value": "no", "label": "Not now"}])
        if picked != "yes":
            return "Not published."
        ref = self.plugin.glorya().publish(job.job_id, slug=slug.split()[0] if slug else None)
        note = self._follow({**ref, "kind": job.kind}, job.kind, job.title)
        return f"Publishing {job.short_id}. I'll post the live link here.{note}"

    def cmd_cancel(self, rest: str, session_key: str) -> str:
        job = self._job(rest.strip(), session_key)
        result = self.plugin.glorya().cancel(job.job_id)
        return f"Glorya: {result.get('status', 'cancelling')} for {job.short_id}."

    def cmd_follow(self, rest: str, session_key: str) -> str:
        ref = rest.strip()
        job = self.plugin.store.find(ref, session_key=session_key) if ref else self._job("", session_key)
        job_id = job.job_id if job else ref
        if not job_id:
            return "Which job? /glorya follow <job id>"
        view = self.plugin.glorya().get_job(job_id)
        if view.get("status") == "completed":
            if self.plugin.follower.deliver_finished(job_id, view):
                return f"{render.headline(str(view.get('kind') or ''), str(view.get('title') or ''))} is ready. Sending the files here."
            return render.result_links(view)
        if view.get("status") in ("failed", "cancelled"):
            return render.status(view, self.plugin.clock())
        note = self._follow({**view, "job_id": job_id}, str(view.get("kind") or ""), str(view.get("title") or ""))
        return f"Glorya job {job_id[:8]}:{note}"

    def cmd_brand(self, rest: str, session_key: str) -> str:
        data = self.plugin.glorya().brand()
        brand = data.get("brand") or {}
        products = data.get("products") or []
        lines = [f"Brand: {brand.get('name') or 'unnamed'}"]
        for key, label in (("website_url", "Website"), ("language", "Language")):
            if brand.get(key):
                lines.append(f"{label}: {brand[key]}")
        if brand.get("description"):
            lines.append(render.clip(brand["description"], 300))
        if products:
            lines.append("Products: " + ", ".join(render.clip(p.get("name"), 40) for p in products[:8]))
        return "\n".join(lines)

    def cmd_credits(self, rest: str, session_key: str) -> str:
        data = self.plugin.glorya().credits()
        plan, credits = data.get("plan") or {}, data.get("credits") or {}
        lines = [f"Credits: {credits.get('total', 0):,}",
                 f"Plan: {plan.get('name') or 'none'} ({plan.get('status') or 'none'})"]
        if plan.get("renews_at"):
            lines.append(f"Renews: {str(plan['renews_at'])[:10]}")
        link = data.get("checkout_url") or data.get("billing_url")
        if link:
            lines.append(f"{'Start a plan' if data.get('checkout_url') else 'Top up'}: {link}")
        return "\n".join(lines)

    def cmd_campaigns(self, rest: str, session_key: str) -> str:
        data = self.plugin.glorya().campaigns(platform=rest.strip().lower() or None)
        campaigns = data.get("campaigns") or []
        if not campaigns:
            return "No campaigns yet. Start one with /glorya campaign <what to advertise>."
        days = (data.get("range") or {}).get("days", 30)
        return f"Campaigns (last {days} days):\n" + "\n".join(
            f"  {render.campaign_line(c)} · spent {render.money(c.get('spend'), c.get('currency'))}"
            + (f" · {c['results']} results" if c.get("results") is not None else "") for c in campaigns)

    def cmd_sites(self, rest: str, session_key: str) -> str:
        sites = self.plugin.glorya().sites().get("sites") or []
        if not sites:
            return "No pages or sites yet. Start one with /glorya page <brief>."
        return "\n".join(f"  {render.label(s.get('kind', ''))} · {render.clip(s.get('name'), 50)} · {s.get('status')}"
                         + f" · {s.get('live_url') or s.get('preview_url') or s.get('open_url')}" for s in sites)

    def cmd_formats(self, rest: str, session_key: str) -> str:
        formats = self.plugin.glorya().formats().get("formats") or []
        return "Video styles (use with /glorya video --format <id> <brief>):\n" + "\n".join(
            f"  {f.get('id')}: {f.get('name')}" for f in formats)
