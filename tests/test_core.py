from __future__ import annotations

import json

import pytest
from conftest import join_followers, mcp_error, mcp_ok, view

from glorya_plugin.client import Glorya, GloryaError, parse_error, parse_result, parse_tool_result

CREATED = {"job_id": "job-1234567890", "kind": "image_ad", "status": "running",
           "open_url": "https://platform.glorya.ai/v2/w/x", "next_step": "Call get_job …"}


def model_result(payload):
    """A model-facing MCP tool result as Hermes builds it."""
    return json.dumps({"result": json.dumps(payload)})


# -- client ---------------------------------------------------------------------------------

def test_parse_error_reads_code_and_links():
    error = parse_error('No plan.\n{"error": "plan_required", "checkout_url": "https://glorya.ai/c"}')
    assert (error.code, error.message, error.link()) == ("plan_required", "No plan.", "https://glorya.ai/c")
    assert parse_error("boom").code == "upstream_error"
    assert parse_error('{"error": "rate_limited", "retry_after_seconds": 5}').data == {"retry_after_seconds": 5}


def test_parse_result_prefers_structured_content():
    assert parse_result({"ok": True, "result": "text", "structuredContent": {"a": 1}}) == {"a": 1}
    assert parse_result({"ok": True, "result": '{"b": 2}'}) == {"b": 2}
    with pytest.raises(GloryaError):
        parse_result({"ok": True, "result": "not json"})
    assert parse_tool_result(json.dumps({"error": "x"})) is None
    assert parse_tool_result(model_result({"job_id": "j"})) == {"job_id": "j"}


def test_client_maps_missing_allowlist_and_drops_empty_args(ctx):
    ctx.script("create_image_ad", mcp_ok(CREATED))
    Glorya(ctx, "glorya").create("image_ad", "Summer sale", references=[], language=None, review=False)
    assert ctx.calls[-1] == ("glorya", "create_image_ad", {"brief": "Summer sale", "review": False})
    ctx.allowed = False
    with pytest.raises(GloryaError) as raised:
        Glorya(ctx, "glorya").brand()
    assert raised.value.code == "not_allowed" and "hermes glorya setup" in raised.value.message


# -- transform_tool_result ------------------------------------------------------------------

def test_create_result_is_handed_to_the_follower(plugin, ctx):
    ctx.script("get_job", mcp_ok(view("completed", kind="image_ad")))
    out = plugin.on_transform_tool_result("mcp__glorya__create_image_ad", {"brief": "x"}, model_result(CREATED))
    join_followers(plugin)
    data = json.loads(json.loads(out)["result"])
    assert data["followed_by_hermes_plugin"] is True and "Don't call get_job" in data["next_step"]
    assert data["job_id"] == CREATED["job_id"] and "::glorya-job" not in data["next_step"]
    assert plugin.store.get(CREATED["job_id"]).session_key == "agent:main:telegram:dm:42"


def test_desktop_chats_get_the_live_card_directive(plugin, ctx):
    ctx.surface = "desktop"
    ctx.script("get_job", mcp_ok(view("completed", kind="image_ad")))
    out = plugin.on_transform_tool_result("mcp__glorya__create_image_ad", {}, model_result(CREATED))
    join_followers(plugin)
    assert '::glorya-job{id="job-1234567890"}' in json.loads(json.loads(out)["result"])["next_step"]


def test_results_are_left_alone_when_not_followed(plugin, ctx):
    assert plugin.on_transform_tool_result("mcp__other__create_image_ad", {}, model_result(CREATED)) is None
    assert plugin.on_transform_tool_result("mcp__glorya__create_image_ad", {}, json.dumps({"error": "x"})) is None
    assert plugin.on_transform_tool_result("mcp__glorya__list_assets", {}, model_result({"assets": []})) is None
    ctx.cron = object()
    assert plugin.on_transform_tool_result("mcp__glorya__create_image_ad", {}, model_result(CREATED)) is None


def test_get_job_results_refresh_tracked_jobs(plugin, store):
    store.track("job-1234567890", kind="video_ad")
    assert plugin.on_transform_tool_result("mcp__glorya__get_job", {"job_id": "job-1234567890"},
                                           model_result(view("needs_input"))) is None
    assert store.get("job-1234567890").status == "needs_input"


def test_custom_server_name(plugin, ctx):
    ctx.settings["server"] = "brand-mcp"
    ctx.script("get_job", mcp_ok(view("completed")))
    assert plugin.on_transform_tool_result("mcp__brand-mcp__create_video_ad", {}, model_result(CREATED))
    join_followers(plugin)
    assert ctx.calls[0][0] == "brand-mcp"


# -- pre_llm_call ---------------------------------------------------------------------------

def test_open_questions_reach_the_model(plugin, store):
    key = "agent:main:telegram:dm:42"
    store.track("job-1234567890", kind="video_ad", title="Serum UGC", session_key=key)
    question = {"request_id": "r1", "kind": "decision", "question": "Which script?", "choices": ["A", "B"]}
    store.save_view("job-1234567890", view("needs_input", questions=[question]))
    context = plugin.on_pre_llm_call(user_message="the second one")["context"]
    assert "request_id r1" in context and "Choices: A | B" in context and "mcp__glorya__respond" in context


def test_no_context_without_recent_jobs(plugin, store, clock):
    assert plugin.on_pre_llm_call() is None
    store.track("old", kind="image_ad", session_key="agent:main:telegram:dm:42")
    store.save_view("old", view("completed", job_id="old"))
    clock.advance(3 * 3600)
    assert plugin.on_pre_llm_call() is None


def test_a_signed_out_glorya_signs_in_through_hermes(plugin):
    plugin.connection = lambda server: "signed_out"
    context = plugin.on_pre_llm_call()["context"]
    assert 'manage_connections now with action "authorize"' in context
    assert '[{"name": "glorya", "mcp": true}]' in context and "don't run commands" in context


def test_a_missing_glorya_points_the_user_to_setup(plugin):
    plugin.connection = lambda server: "missing"
    context = plugin.on_pre_llm_call()["context"]
    assert "hermes glorya setup" in context and "nothing to restart" in context


# -- native tools ---------------------------------------------------------------------------

def test_glorya_attach_returns_media_lines(plugin, ctx):
    asset = {"id": "a1", "type": "video", "url": "https://media.glorya.ai/a1.mp4"}
    ctx.script("get_job", mcp_ok(view("completed", assets=[asset])))
    out = json.loads(plugin.tool_attach({"job_id": "job-1234567890"}))
    assert out["reply_lines"] == [f"MEDIA:{out['files'][0]['path']}"]


def test_glorya_attach_reports_unfinished_and_errors(plugin, ctx):
    ctx.script("get_job", mcp_ok(view("running")))
    assert json.loads(plugin.tool_attach({"job_id": "j"}))["files"] == []
    ctx.responses["get_job"] = [mcp_error("job_not_found", "No job.")]
    assert json.loads(plugin.tool_attach({"job_id": "j"}))["code"] == "job_not_found"
    assert "error" in json.loads(plugin.tool_attach({}))


def test_housekeeping_prunes_old_jobs_and_files(plugin, store, clock, tmp_path):
    store.track("old-job-000", kind="image_ad")
    store.save_view("old-job-000", view("completed", job_id="old-job-000"))
    (tmp_path / "media" / "old-job-000").mkdir(parents=True)
    (tmp_path / "media" / "old-job-000" / "a.png").write_bytes(b"x")
    store.track("new-job-000", kind="image_ad")
    clock.advance(31 * 86400)
    store.track("new-job-000", kind="image_ad")
    plugin.housekeep()
    assert store.get("old-job-000") is None and store.get("new-job-000") is not None
    assert not (tmp_path / "media" / "old-job-000").exists()


def test_plugin_tools_never_share_the_mcp_servers_toolset_name():
    from glorya_plugin import TOOLSET
    from glorya_plugin.settings import Settings

    assert TOOLSET != Settings().server and not TOOLSET.startswith("mcp-")


# -- pre_tool_call ----------------------------------------------------------------------------

def test_campaigns_and_publishing_need_hermes_approval(plugin):
    directive = plugin.on_pre_tool_call("mcp__glorya__create_campaign",
                                        {"brief": "new serum", "platform": "meta", "daily_budget": 40})
    assert directive == {"action": "approve", "rule_key": "glorya:campaign",
                         "message": "Glorya · Meta, 40/day: launch a paid ad campaign from your ad account? Brief: new serum"}
    assert "default budget" in plugin.on_pre_tool_call("mcp__glorya__create_campaign", {"brief": "x"})["message"]
    assert plugin.on_pre_tool_call("mcp__glorya__publish_site", {"job_id": "j"})["rule_key"] == "glorya:publish"
    for tool in ("mcp__glorya__create_image_ad", "mcp__glorya__get_job", "glorya_attach", "mcp__other__create_campaign"):
        assert plugin.on_pre_tool_call(tool, {}) is None


def test_approval_matches_the_name_hermes_gives_a_hyphenated_server(plugin, ctx):
    ctx.settings["server"] = "brand-mcp"
    assert plugin.on_pre_tool_call("mcp__brand_mcp__create_campaign", {})["action"] == "approve"
    assert plugin.on_pre_tool_call("mcp__brand-mcp__create_campaign", {})["action"] == "approve"


def test_approval_survives_odd_arguments(plugin):
    message = plugin.on_pre_tool_call("mcp__glorya__create_campaign",
                                      {"daily_budget": "lots", "platform": None, "review": True})["message"]
    assert "default budget" in message and "approve the ads before launch" in message


def test_register_declares_every_hook_it_registers(plugin, monkeypatch):
    import itertools

    import glorya_plugin
    from conftest import ROOT, FakeCtx

    class Recorder(FakeCtx):
        def __init__(self):
            super().__init__()
            self.hooks: list[str] = []

        def register_hook(self, name, callback, **_):
            self.hooks.append(name)

        def __getattr__(self, name):
            return lambda *a, **k: None

    recorder = Recorder()
    monkeypatch.setattr(glorya_plugin, "GloryaPlugin", lambda _ctx: plugin)
    glorya_plugin.register(recorder)
    lines = (ROOT / "plugin.yaml").read_text().split("provides_hooks:\n", 1)[1].splitlines()
    declared = [line[4:] for line in itertools.takewhile(lambda line: line.startswith("  - "), lines)]
    assert "pre_tool_call" in recorder.hooks and sorted(recorder.hooks) == sorted(declared)


def test_job_ids_are_made_safe_before_naming_a_folder(plugin, ctx, tmp_path):
    asset = {"id": "a1", "type": "video", "url": "https://media.glorya.ai/a1.mp4"}
    ctx.script("get_job", mcp_ok(view("completed", assets=[asset])))
    out = json.loads(plugin.tool_attach({"job_id": "../../etc/x"}))
    folder = (tmp_path / "media").resolve()
    assert all(str(__import__("pathlib").Path(f["path"]).resolve()).startswith(str(folder) + "/") for f in out["files"])


def test_existing_site_publish_and_campaign_resume_require_approval(plugin):
    assert plugin.on_pre_tool_call("mcp__glorya__publish_existing_site", {"site_id": "site1"})["rule_key"] == "glorya:publish"
    directive = plugin.on_pre_tool_call("mcp__glorya__set_campaign_status", {"campaign_id": "campaign1", "status": "active"})
    assert directive["action"] == "approve"
    assert "budget" in directive["message"]
    assert "campaign1" in directive["message"]
