---
name: glorya
description: Make on-brand image ads, video ads, landing pages and websites with Glorya in Hermes. Use it whenever the user asks for an ad, a video ad, a landing page or a website for their brand, or mentions Glorya.
---

# Glorya in Hermes

Glorya is an AI marketing agent that already knows the user's brand: logo, colors, fonts, products and language. In Hermes, the Glorya plugin follows each job in the background and reports in the chat by itself. You start the work and step back.

Every MCP tool, input, status, error and limit is in [references/tools.md](references/tools.md). In Hermes, `create_campaign` and `publish_site` always wait for the user's OK in Hermes' approval prompt, even where tools.md says Glorya launches without asking.

## Connect

The tools come from the Glorya MCP server (`mcp__glorya__*`, `https://platform.glorya.ai/mcp`, signed in with the user's Glorya account). If they are missing, sign in through Hermes: call `manage_connections` with action `authorize` and connectors `[{"name": "glorya", "mcp": true}]`. It keeps a working sign-in, or gives a link for the user to open on the computer running Hermes. Never run `hermes` commands yourself. If Hermes says glorya isn't a configured server, tell the user to run `hermes glorya setup` in their own terminal.

## Rules

- Use the default brand: leave `workspace` empty. Only when the user names another brand, call `list_workspaces` with `query` set to that name and pass the matching `id` as `workspace`.
- Start right away. Pass the user's own words as `brief`. With no details, pass what they asked for, such as "Create an image ad".
- Ask nothing before you start: not the format, size, language, audience or style. Glorya picks these.
- Set `language`, `format` or `references` only when the user gave them. `references` are public https links.
- Leave `review` out. Set `review: true` only when the user asks to review or approve steps ("let me review", "show me the script first").
- Never invent products, prices or offers. Never start the same job twice.

## After you start a job

- If the tool result has `followed_by_hermes_plugin: true`, the plugin owns the job. Say in one short sentence that Glorya started and share `open_url`, then end your turn. Don't call `get_job` for it. The plugin edits a progress message, posts Glorya's questions and posts the finished files in this chat.
- If the result says so, put the `::glorya-job{id="…"}` line in your reply (desktop chats only): it shows a live card.
- Otherwise (a scheduled run, or a chat the plugin can't post to), run the loop yourself: call `get_job` with `wait_seconds: 30` until the status is `needs_input`, `completed`, `failed` or `cancelled`.

## Questions, changes and results

- The plugin adds a note about this chat's Glorya jobs to the user's message, with any open question, its `request_id` and exact `choices`. When the user's message answers it, call `respond` with `job_id`, `request_id` and the exact label (their own words for `input`, `revise` and `clarify`). Don't answer for the user and don't add questions of your own.
- For changes ("make the headline shorter", "calmer voice"), call `refine` with the job's `job_id` and the user's words. The plugin follows it again.
- To send finished files into the chat yourself, call `glorya_attach` with the `job_id` and put each of its `reply_lines` (`MEDIA:/…`) in your reply exactly as written.
- `glorya_jobs` lists the jobs the plugin follows, in this chat or all chats.
- Publish a landing page or website only when the user says so ("publish it", "make it live"): call `publish_site`. Hermes asks the user to confirm first; the plugin posts the live link.

## Video styles

Set `format` only if the user named a style. Call `list_video_formats` and pass the matching `id`.

## When something fails

Pass the error message and its link on; don't retry in a loop.

- `plan_required`: share `checkout_url` ($99/month Starter plan).
- `no_credits`: share `billing_url`.
- `setting_up`: the brand is still setting up; try again in a few minutes.
- `limit_reached`: up to 3 jobs run at once per brand. Wait, or stop an ad with `cancel_job`.

## Campaigns

- "Run ads for …", "launch a campaign": call `create_campaign` with the user's words as `brief`. Set `platform`, `daily_budget`, `goal` or `destination` only when the user said them.
- A campaign spends real money from the user's ad account. Hermes asks the user to approve every `create_campaign` call (platform and daily budget) before it runs; if they decline, say so in one line and stop. Set `review: true` only when the user also wants to see the ads before launch.
- Default budget is 30 a day in the ad account's currency (TikTok 50). `integration_required`: share `connect_url` so the user connects the ad account.
- "How are my ads doing?": `list_campaigns`. Connected ad accounts: `get_integrations`.

## Credits and pages

- "How many credits do I have?": `get_credits`. Share `billing_url` to top up, or `checkout_url` when there is no plan.
- Their landing pages and websites: `list_sites`.

## Never

- Publish a page or site without an explicit ask.

## The user can also type

`/glorya image|video|page|site|campaign <brief>`, `/glorya jobs`, `/glorya answer`, `/glorya refine <change>`, `/glorya publish`, `/glorya cancel`, `/glorya credits`, `/glorya campaigns`. These run without you.
