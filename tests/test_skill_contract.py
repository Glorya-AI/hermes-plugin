"""Check the packaged agent-facing contract, which is installed independently of the server."""

from conftest import ROOT
from glorya_plugin.client import CREATE_TOOLS
from glorya_plugin.core import APPROVAL_RULES


def test_packaged_skill_preserves_the_conversation_brand():
    skill = (ROOT / "skills/glorya/SKILL.md").read_text()
    assert "leave `workspace` empty" not in skill
    assert "every subsequent brand-specific call" in skill
    assert "/glorya switch default" in skill
    reference = (ROOT / "skills/glorya/references/tools.md").read_text()
    assert "Set only when the user named another brand" not in reference
    assert "organization_id" in reference


def test_packaged_recovery_contract_covers_remote_history_and_create_keys():
    reference = (ROOT / "skills/glorya/references/tools.md").read_text()
    sections = {section.split("`", 1)[0]: section for section in reference.split("### `")[1:]}
    assert {"list_jobs", *CREATE_TOOLS.values()} <= sections.keys()
    for tool in CREATE_TOOLS.values():
        assert "| `idempotency_key` |" in sections[tool]
    assert "pending_starts" in sections["list_jobs"]
    assert "next_cursor" in sections["list_jobs"]
    skill = (ROOT / "skills/glorya/SKILL.md").read_text()
    assert "creation_pending" in skill and "creation_uncertain" in skill
    assert "/glorya jobs remote" in skill


def test_packaged_management_contract_documents_tools_and_hermes_approvals():
    skill = (ROOT / "skills/glorya/SKILL.md").read_text()
    reference = (ROOT / "skills/glorya/references/tools.md").read_text()
    sections = {section.split("`", 1)[0]: section for section in reference.split("### `")[1:]}
    management = {"get_site", "edit_site", "publish_existing_site", "get_campaign_report", "set_campaign_status"}
    assert management <= sections.keys()
    for tool in APPROVAL_RULES:
        assert f"`{tool}`" in skill
    for tool in management:
        assert "| `workspace` |" in sections[tool]
    assert "| `site_id` |" in sections["publish_existing_site"]
    assert "| `campaign_id` |" in sections["set_campaign_status"]
    assert "poll `get_site`" in skill

