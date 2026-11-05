from __future__ import annotations

import pytest
from conftest import join_followers, mcp_error, mcp_ok, view

from glorya_plugin.commands import Commands, _flags

KEY = "agent:main:telegram:dm:42"
QUESTION = {"request_id": "r1", "kind": "decision", "question": "Which script?", "choices": ["Script A", "Script B"]}


@pytest.fixture
def glorya(plugin):
    return Commands(plugin)


def created(kind="video_ad"):
    return mcp_ok({"job_id": "job-1234567890", "kind": kind, "status": "running", "open_url": "https://g/x"})


def test_flags_are_pulled_out_of_the_brief():
    assert _flags("--format ugc a serum ad --review") == ({"format": "ugc", "review": True}, "a serum ad")
    assert _flags("--format=street-interview hi") == ({"format": "street_interview"}, "hi")


def test_video_command_starts_and_follows(glorya, plugin, ctx):
    ctx.script("create_video_ad", created())
    ctx.script("get_job", mcp_ok(view("completed")))
    reply = glorya("video --format ugc new serum, make it punchy", session_key=KEY)
    join_followers(plugin)
    assert ctx.calls[0] == ("glorya", "create_video_ad",
                            {"brief": "new serum, make it punchy", "format": "ugc"})
    assert "started. Updates follow in this chat." in reply


def test_page_command_drops_ad_only_flags(glorya, ctx, plugin):
    ctx.script("create_landing_page", created("landing_page"))
    ctx.script("get_job", mcp_ok(view("completed", kind="landing_page")))
    glorya("page --review --format ugc spring launch", session_key=KEY)
    join_followers(plugin)
    assert ctx.calls[0][2] == {"brief": "spring launch"}


def test_answer_with_buttons(glorya, plugin, ctx, store):
    store.track("job-1234567890", kind="video_ad", session_key=KEY)
    ctx.script("get_job", mcp_ok(view("needs_input", questions=[QUESTION])), mcp_ok(view("completed")))
    ctx.script("respond", mcp_ok({"status": "submitted"}))
    ctx.choices = ["Script B"]
    reply = glorya("answer", session_key=KEY)
    join_followers(plugin)
    respond = [call for call in ctx.calls if call[1] == "respond"][0]
    assert respond[2] == {"job_id": "job-1234567890", "answer": "Script B", "request_id": "r1"}
    assert reply.startswith('Sent "Script B"')


def test_answer_by_number(glorya, plugin, ctx, store):
    store.track("job-1234567890", kind="video_ad", session_key=KEY)
    ctx.script("get_job", mcp_ok(view("needs_input", questions=[QUESTION])), mcp_ok(view("completed")))
    ctx.script("respond", mcp_ok({"status": "submitted"}))
    glorya("answer job-1234 1", session_key=KEY)
    join_followers(plugin)
    assert [call for call in ctx.calls if call[1] == "respond"][0][2]["answer"] == "Script A"


def test_publish_needs_confirmation(glorya, ctx, store):
    store.track("job-1234567890", kind="landing_page", session_key=KEY)
    ctx.choices = ["no"]
    assert glorya("publish", session_key=KEY) == "Not published."
    assert not ctx.calls


def test_publish_refuses_ads(glorya, store):
    store.track("job-1234567890", kind="image_ad", session_key=KEY)
    assert "only landing pages and websites" in glorya("publish", session_key=KEY)


def test_errors_become_messages(glorya, ctx):
    ctx.script("create_image_ad", mcp_error("plan_required", "Start a plan.", checkout_url="https://glorya.ai/c"))
    assert glorya("image summer sale", session_key=KEY) == "Glorya: Start a plan.\nhttps://glorya.ai/c"


def test_help_unknown_and_empty(glorya, store):
    assert glorya("", session_key=KEY).startswith("Glorya — on-brand")
    assert "Unknown /glorya command 'dance'" in glorya("dance", session_key=KEY)
    assert "Tell Glorya what to make" in glorya("image", session_key=KEY)
    assert "No Glorya job in this chat yet" in glorya("status", session_key=KEY)


def test_jobs_lists_this_chat(glorya, store):
    store.track("job-1234567890", kind="image_ad", title="Summer sale", session_key=KEY)
    store.track("job-other-0000", kind="video_ad", session_key="elsewhere")
    listing = glorya("jobs", session_key=KEY)
    assert "job-1234" in listing and "job-othe" not in listing
    assert "job-othe" in glorya("jobs all", session_key=KEY)


def test_following_a_finished_job_sends_its_files(glorya, plugin, ctx):
    image = {"id": "img1", "type": "image", "url": "https://media.glorya.ai/img1.png", "label": "feed"}
    ctx.script("get_job", mcp_ok(view("completed", kind="image_ad", assets=[image])))
    reply = glorya("follow job-1234567890", session_key=KEY)
    assert "Sending the files here" in reply
    assert len(ctx.injected) == 1 and "MEDIA:" in ctx.injected[0]["content"]
    job = plugin.store.get("job-1234567890")
    assert job.status == "completed" and job.delivered == ["img1"] and job.session_key == KEY
    assert glorya("follow job-1234567890", session_key=KEY).startswith("✅")  # nothing new: links only


def test_campaign_command_passes_platform_and_budget(glorya, plugin, ctx):
    ctx.script("create_campaign", created("campaign"))
    ctx.script("get_job", mcp_ok(view("completed", kind="campaign", campaign={
        "platform": "meta", "stage": "ready", "daily_budget": 30, "currency": "EUR", "ad_account_id": "act_1",
        "campaign_id": None, "manage_url": "https://platform.glorya.ai/v2/app/w/ws-1/campaigns"})))
    ctx.choices = ["yes"]
    reply = glorya("campaign --platform meta --budget 40 new serum, women 25-45", session_key=KEY)
    join_followers(plugin)
    assert ctx.calls[0] == ("glorya", "create_campaign",
                            {"brief": "new serum, women 25-45", "platform": "meta", "daily_budget": 40})
    assert "Ad campaign started" in reply
    assert "Meta · ready · 30 EUR/day" in ctx.posts[-1]
    assert "Manage: https://platform.glorya.ai/v2/app/w/ws-1/campaigns" in ctx.posts[-1]


def test_campaign_budget_must_be_a_number(glorya, ctx):
    assert "whole number" in glorya("campaign --budget lots serum", session_key=KEY)
    assert not ctx.calls


def test_credits_and_campaigns(glorya, ctx):
    ctx.script("get_credits", mcp_ok({"plan": {"name": "Starter", "status": "active", "renews_at": "2026-12-01T00:00:00Z"},
                                      "credits": {"total": 1234}, "billing_url": "https://g/billing", "checkout_url": None}))
    assert glorya("credits", session_key=KEY) == ("Credits: 1,234\nPlan: Starter (active)\nRenews: 2026-12-01\n"
                                                  "Top up: https://g/billing")
    ctx.script("list_campaigns", mcp_ok({"range": {"days": 30}, "campaigns": [
        {"platform": "google_ads", "name": "Search", "status": "active", "daily_budget": 20, "currency": "USD",
         "spend": 412.5, "results": 18}]}))
    assert "Google Ads · Search · active · 20 USD/day · spent 412.50 USD · 18 results" in glorya("campaigns", session_key=KEY)


def test_campaign_budget_without_a_currency_reads_cleanly():
    from glorya_plugin.render import campaign_line
    assert campaign_line({"platform": "google_ads", "name": "DSA", "status": "paused", "daily_budget": 1.5}) == \
        "Google Ads · DSA · paused · 1.5/day"


def test_campaign_command_asks_before_spending(glorya, ctx):
    ctx.choices = ["no"]
    assert glorya("campaign --platform tiktok --budget 50 serum", session_key=KEY) == "No campaign started."
    assert glorya("campaign serum", session_key=KEY) == "No campaign started."  # no answer: nothing starts
    assert not ctx.calls
