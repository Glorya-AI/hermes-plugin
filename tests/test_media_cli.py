from __future__ import annotations

import io

import pytest

from glorya_plugin import cli, media, render


class Response(io.BytesIO):
    def __init__(self, body: bytes, content_type: str = "video/mp4", url: str = "https://media.glorya.ai/a.mp4",
                 length: bool = True):
        super().__init__(body)
        self.headers = {"Content-Type": content_type, **({"Content-Length": str(len(body))} if length else {})}
        self._url = url

    def geturl(self):
        return self._url


def opener(response):
    return lambda url, timeout: response


def public(_host):
    return True


def test_download_writes_atomically(tmp_path):
    path = media.download("https://media.glorya.ai/a.mp4", tmp_path, "a1", 100,
                          opener=opener(Response(b"x" * 10)), host_check=public)
    assert path.name == "a1.mp4" and path.read_bytes() == b"x" * 10
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".part-")]


@pytest.mark.parametrize("url", ["http://media.glorya.ai/a.mp4", "https://user:pw@media.glorya.ai/a.mp4", "file:///etc/passwd"])
def test_download_refuses_unsafe_links(tmp_path, url):
    with pytest.raises(ValueError):
        media.download(url, tmp_path, "a", 100, opener=opener(Response(b"x")), host_check=public)


def test_download_refuses_private_hosts(tmp_path):
    with pytest.raises(ValueError):
        media.download("https://media.glorya.ai/a.mp4", tmp_path, "a", 100, opener=opener(Response(b"x")),
                       host_check=lambda _h: False)


def test_download_caps_size_without_content_length(tmp_path):
    with pytest.raises(media.TooLarge):
        media.download("https://media.glorya.ai/a.mp4", tmp_path, "a", 5,
                       opener=opener(Response(b"x" * 10, length=False)), host_check=public)
    assert list(tmp_path.iterdir()) == []


def test_download_refuses_non_media(tmp_path):
    with pytest.raises(ValueError):
        media.download("https://media.glorya.ai/a", tmp_path, "a", 100,
                       opener=opener(Response(b"<html>", "text/html", "https://media.glorya.ai/a")), host_check=public)


def test_fetch_assets_puts_videos_first_and_keeps_links(tmp_path):
    assets = [{"id": "i1", "type": "image", "url": "https://media.glorya.ai/i1.png"},
              {"id": "v1", "type": "video", "url": "https://media.glorya.ai/v1.mp4"}]
    files, links = media.fetch_assets(assets, tmp_path, 100, limit=1, opener=opener(Response(b"x")), host_check=public)
    assert [f["asset_id"] for f in files] == ["v1"] and [a["id"] for a in links] == ["i1"]


def test_delivery_turn_lists_media_lines():
    turn = render.delivery_turn({"job_id": "j", "kind": "video_ad", "progress": "Headline: Glow",
                                 "open_url": "https://g/x"}, [{"path": "/tmp/a.mp4"}])
    assert "MEDIA:/tmp/a.mp4" in turn and "Headline: Glow" in turn and "Don't call any tool" in turn


# -- hermes glorya setup / status -----------------------------------------------------------

READY = {
    "plugins": {"enabled": ["glorya"], "entries": {"glorya": {"mcp_allowlist": ["glorya"],
                                                               "allow_gateway_injection": True}}},
    "mcp_servers": {"glorya": {"url": "https://platform.glorya.ai/mcp", "auth": "oauth"}},
}


def test_check_reports_each_requirement():
    assert all(ok for _, ok, _ in cli.check(READY))
    missing = {name: fix for name, ok, fix in cli.check({}) if not ok}
    assert "hermes mcp add glorya --url https://platform.glorya.ai/mcp --auth oauth" in missing.values()
    assert "hermes config set plugins.entries.glorya.mcp_allowlist '[\"glorya\"]'" in missing.values()


def test_setup_runs_only_what_the_user_accepts():
    ran, out = [], []
    answers = iter(["y", "y", "n", "y", "n"])
    cli.setup(interactive=True, run=lambda argv: ran.append(argv[1:]) or 0, read=lambda _q: next(answers),
              load=lambda: {}, out=out.append, hermes=["hermes"])
    assert ran == [["plugins", "enable", "glorya"],
                   ["mcp", "add", "glorya", "--url", "https://platform.glorya.ai/mcp", "--auth", "oauth"],
                   ["config", "set", "plugins.entries.glorya.allow_gateway_injection", "true"]]
    assert any("skipped: plugin may call 'glorya'" in line for line in out)


def test_setup_without_a_terminal_prints_commands():
    out = []
    cli.setup(interactive=False, run=lambda argv: pytest.fail("ran a command"), load=lambda: {}, out=out.append)
    assert any("hermes mcp login glorya" in line for line in out)


def test_status_exit_code():
    assert cli.status(load=lambda: READY, out=lambda _l: None) == 0
    assert cli.status(load=lambda: {}, out=lambda _l: None) == 1
