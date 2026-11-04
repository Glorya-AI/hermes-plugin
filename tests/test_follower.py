from __future__ import annotations

import json

from conftest import join_followers, mcp_error, mcp_ok, view

JOB = "job-1234567890"
VIDEO = {"id": "a1", "type": "video", "url": "https://media.glorya.ai/a1.mp4", "label": "Final cut"}
QUESTION = {"request_id": "r1", "kind": "decision", "question": "Which script?", "choices": ["Script A", "Script B"]}


def test_follows_a_video_ad_to_attachments(plugin, ctx):
    ctx.script("get_job",
               mcp_ok(view("running", progress="Writing the script")),
               mcp_ok(view("needs_input", questions=[QUESTION])),
               mcp_ok(view("needs_input", questions=[QUESTION])),
               mcp_ok(view("running", progress="Rendering")),
               mcp_ok(view("completed", progress="Headline: Glow in 7 days", assets=[VIDEO])))

    assert plugin.follower.start(JOB, kind="video_ad", title="Serum UGC", open_url="https://platform.glorya.ai/x")
    join_followers(plugin)

    assert ctx.posts[0].startswith("🎬 Glorya · Video ad · Serum UGC")
    assert any("Writing the script" in text for text in ctx.edits)
    assert any(text.endswith("Open in Glorya: https://platform.glorya.ai/v2/w/x") for text in ctx.edits)
    questions = [p for p in ctx.posts if "needs your answer" in p]
    assert len(questions) == 1 and "1. Script A" in questions[0]
    assert len(ctx.injected) == 1
    delivery = ctx.injected[0]
    assert delivery["session_key"] == "agent:main:telegram:dm:42"
    assert "MEDIA:" in delivery["content"] and "a1.mp4" in delivery["content"]
    job = plugin.store.get(JOB)
    assert job.status == "completed" and job.delivered == ["a1"] and job.asked == ["r1"]
    assert all(call[2]["wait_seconds"] == 30 for call in ctx.calls)


def test_falls_back_to_links_without_injection(plugin, ctx):
    ctx.inject_result = False
    ctx.script("get_job", mcp_ok(view("completed", assets=[VIDEO])))
    assert plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    assert ctx.posts[-1].startswith("✅") and VIDEO["url"] in ctx.posts[-1]
    assert plugin.store.get(JOB).delivered == ["a1"]


def test_posts_links_when_deliver_is_links(plugin, ctx):
    ctx.settings["deliver"] = "links"
    ctx.script("get_job", mcp_ok(view("completed", assets=[VIDEO])))
    plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    assert not ctx.injected and VIDEO["url"] in ctx.posts[-1] and not plugin.fetched


def test_site_completion_posts_preview(plugin, ctx):
    site = {"kind": "landing_page", "status": "ready", "preview_url": "https://preview.glorya.ai/p", "live_url": None,
            "publish_status": None}
    ctx.script("get_job", mcp_ok(view("completed", kind="landing_page", site=site)))
    plugin.follower.start(JOB, kind="landing_page")
    join_followers(plugin)
    assert "Preview: https://preview.glorya.ai/p" in ctx.posts[-1] and "Not live yet" in ctx.posts[-1]


def test_failure_is_reported(plugin, ctx):
    ctx.script("get_job", mcp_ok(view("failed", error="Render failed")))
    plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    assert "failed: Render failed" in ctx.posts[-1]


def test_does_not_follow_in_cron_or_without_a_chat(plugin, ctx):
    ctx.cron = object()
    assert plugin.follower.start(JOB, kind="image_ad") is False
    ctx.cron = None
    ctx.post_ok = False
    assert plugin.follower.start(JOB, kind="image_ad") is False
    ctx.post_ok = True
    ctx.settings["follow"] = False
    assert plugin.follower.start(JOB, kind="image_ad") is False
    assert not ctx.calls


def test_gives_up_after_repeated_errors(plugin, ctx):
    ctx.script("get_job", mcp_error("upstream_error", "Glorya is down"))
    plugin.follower.start(JOB, kind="image_ad")
    join_followers(plugin)
    assert len(ctx.calls) == 8
    assert "can't reach job job-1234" in ctx.posts[-1]


def test_stops_on_fatal_error(plugin, ctx):
    ctx.script("get_job", mcp_error("job_not_found", "No job with that id."))
    plugin.follower.start(JOB, kind="image_ad")
    join_followers(plugin)
    assert len(ctx.calls) == 1 and "No job with that id." in ctx.edits[-1]


def test_refollowing_delivers_only_new_assets(plugin, ctx):
    ctx.script("get_job", mcp_ok(view("completed", assets=[VIDEO])))
    plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    second = {"id": "a2", "type": "video", "url": "https://media.glorya.ai/a2.mp4"}
    ctx.responses["get_job"] = [mcp_ok(view("completed", assets=[second, VIDEO]))]
    plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    assert "a2.mp4" in ctx.injected[-1]["content"] and "a1.mp4" not in ctx.injected[-1]["content"]
    assert plugin.store.get(JOB).delivered == ["a1", "a2"]


def test_cancelled_job(plugin, ctx):
    ctx.script("get_job", mcp_ok(view("cancelled")))
    plugin.follower.start(JOB, kind="video_ad")
    join_followers(plugin)
    assert "stopped" in ctx.posts[-1]
    assert json.loads(plugin.tool_jobs({"scope": "all"}))["jobs"][0]["status"] == "cancelled"
