# Glorya for Hermes

**Ask Hermes for an ad. Get the finished video back in your chat.**

[Glorya](https://glorya.ai) already knows your brand: logo, colors, fonts, products. Tell Hermes what you want, like "video ad for our new serum", and the plugin does the rest:

1. It starts the job and keeps one message updated while Glorya works.
2. When Glorya needs a choice, it asks you in the chat. Reply, or tap a button.
3. It sends the finished video or images back as real files.

Works in Telegram, Discord, Slack, WhatsApp, the terminal and Hermes Desktop. Makes image ads, video ads, landing pages and websites.

Also included:

- `/glorya video new serum launch` starts a job without the AI model. `jobs`, `answer`, `refine`, `publish` and `cancel` work the same way.
- Weekly autopilot: fresh image ads or a video ad posted to your chat every week (`/blueprint glorya:weekly-video-ad`).
- Hermes Desktop: a Glorya Studio tab with every job, its videos and its questions.

## Requirements

- Hermes Agent 0.22.5 or newer.
- A Glorya account with an active plan ($99/month Starter at [glorya.ai](https://glorya.ai)). Jobs use your Glorya credits, the same as in the Glorya platform.

## Install

```bash
hermes plugins install glorya --enable    # from the Hermes plugin catalog, once listed
# or straight from this repo:
hermes plugins install Glorya-AI/hermes-plugin --enable

hermes glorya setup                       # connect Glorya and grant what the plugin needs
hermes gateway restart
```

`hermes glorya setup` asks before each step and only runs Hermes' own commands:

1. `hermes plugins enable glorya`
2. `hermes mcp add glorya --url https://platform.glorya.ai/mcp --auth oauth`: adds the Glorya MCP server. Hermes signs in with OAuth and keeps the token. The plugin never sees it.
3. `hermes config set plugins.entries.glorya.mcp_allowlist '["glorya"]'`: lets the plugin call that server through `ctx.call_mcp`, so it can follow jobs.
4. `hermes config set plugins.entries.glorya.allow_gateway_injection true`: optional. Lets the plugin start one short agent turn in a chat when a job finishes, so the files arrive as attachments. Without it you get links.
5. `hermes mcp login glorya`: opens the browser to sign in to Glorya and pick a default brand.

Check the result any time with `hermes glorya status`.

## Use it

Just ask:

> Make a UGC video ad for our new serum
> Image ad for the summer sale, let me review the concept first
> Landing page for the spring collection
> Make the headline shorter · Publish it

Or type:

```
/glorya image summer sale for our bestseller
/glorya video --format ugc --review new serum, first week offer
/glorya page spring collection launch
/glorya jobs
/glorya answer            # choices as buttons
/glorya refine make the background darker
/glorya publish my-spring-page
/glorya cancel
/glorya brand | formats
```

Scheduled: `/blueprint glorya:weekly-image-ads` or `/blueprint glorya:weekly-video-ad`, or pick them on the Desktop Cron page.

In Hermes Desktop: ⌘K → **Glorya: open studio**.

## If something is off

| What you see | What to do |
| --- | --- |
| Hermes doesn't know about Glorya | Run `hermes glorya status`, fix what it lists, then `hermes gateway restart`. |
| "Start a plan" with a link | Open the link, start the plan, then ask again. |
| "Brand still setting up" | Finish your brand in the browser and try again in a few minutes. |
| Sign-in expired | Run `hermes mcp login glorya`. |
| Links instead of files | Run `hermes glorya setup` again and say yes to sending files. Telegram bots upload up to 50 MB; bigger files come as links. |

Full walkthrough: [glorya.ai/docs/mcp/hermes](https://glorya.ai/docs/mcp/hermes).

## Settings

Settings → Plugins → Glorya in Desktop, or `plugins.entries.glorya.settings` in `config.yaml`:

| Key | Default | |
| --- | --- | --- |
| `server` | `glorya` | The `mcp_servers` entry for `https://platform.glorya.ai/mcp`. |
| `follow` | `true` | Follow jobs in the background. With `false`, the model polls with `get_job`. |
| `deliver` | `attach` | `attach` sends files as attachments (needs `allow_gateway_injection`); `links` posts links. |
| `attach_max_mb` | `45` | Larger files are sent as links. Telegram bots can upload up to 50 MB. |
| `follow_minutes` | `90` | Stop following a job after this long. |

## How it works

The Glorya MCP server does the work. Hermes connects to it with OAuth, and the model uses its tools (`mcp__glorya__create_video_ad`, …).

1. A `transform_tool_result` hook sees a Glorya create, refine, answer or publish result. It posts a progress message, starts a background follower and tells the model the plugin has the job, so the turn ends right away.
2. The follower long-polls `get_job` through `ctx.call_mcp` (Hermes' own MCP client and token) and edits the message as the job moves. It runs in a copy of the turn's context, so it keeps posting to that chat.
3. Glorya's questions are posted once each. A `pre_llm_call` hook tells the model about this chat's open questions and recent jobs, so "the second script" or "make it calmer" goes to the right job.
4. When the job finishes, the follower downloads the files into the plugin's data folder. It then injects one turn so the agent replies with `MEDIA:` attachments. Without that grant, or if a file is too big, it posts links.
5. Scheduled runs and chats without a live gateway are left to the model. It follows the job with `get_job` and attaches files with `glorya_attach`.

Native tools: `glorya_attach` (download a finished job's files and return `MEDIA:` lines) and `glorya_jobs` (the jobs the plugin follows).

## What it does on your machine (disclosure)

- **Network:** Glorya tool calls go to `https://platform.glorya.ai/mcp` through Hermes' MCP client, using your Glorya sign-in. Finished files are downloaded over https from the links Glorya returns: https only, public hosts only, size-capped. Nothing else is contacted. No telemetry or analytics.
- **Credits:** creating, refining and answering jobs uses your Glorya credits. Publishing puts a page on the internet. It only happens when you ask, and `/glorya publish` asks you to confirm first.
- **Data:** the plugin keeps a SQLite file and downloaded files under `<HERMES_HOME>/plugin-data/glorya/`. The file holds job ids, titles, statuses, the chat a job belongs to (session key and id) and file paths. Finished jobs older than 30 days are pruned.
- **Agent turns:** with `allow_gateway_injection`, the plugin starts one agent turn in the job's chat when files are ready. That turn costs one model call.
- **Shell:** only `hermes glorya setup` runs commands, and only the `hermes …` commands listed above, each after you say yes.
- **Credentials:** none are read or stored by the plugin. Hermes holds the Glorya OAuth token.
- **Background threads:** one daemon thread per followed job (at most 8). Each stops when the job finishes, fails or runs past `follow_minutes`.
- **Hermes internals:** to route updates to the right chat, the plugin reads the session key with `gateway.session_context.get_session_env`, as the plugin guide documents.

## Develop

```bash
uv run --no-project --with 'pytest>=8,<9' python -m pytest -q
hermes plugins validate . && hermes plugins doctor . --ci
```

The folder must be named `glorya` (a valid Python package name), as it is when Hermes installs it.

## License

MIT
