"""Check the packaged agent-facing contract, which is installed independently of the server."""

from conftest import ROOT
from glorya_plugin.client import CREATE_TOOLS


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

