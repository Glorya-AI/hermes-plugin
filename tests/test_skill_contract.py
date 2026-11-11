"""Check the packaged agent-facing contract, which is installed independently of the server."""

from conftest import ROOT


def test_packaged_skill_preserves_the_conversation_brand():
    skill = (ROOT / "skills/glorya/SKILL.md").read_text()
    assert "leave `workspace` empty" not in skill
    assert "every subsequent brand-specific call" in skill
    assert "/glorya switch default" in skill
    reference = (ROOT / "skills/glorya/references/tools.md").read_text()
    assert "Set only when the user named another brand" not in reference
    assert "organization_id" in reference

