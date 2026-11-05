---
name: glorya
description: Make on-brand image ads, video ads, landing pages and websites with Glorya in Hermes. Use it whenever the user asks for an ad, a video ad, a landing page or a website for their brand, or mentions Glorya.
---

# Glorya in Hermes

Glorya is an AI marketing agent that already knows the user's brand: logo, colors, fonts, products and language. In Hermes, the Glorya plugin follows each job in the background and reports in the chat by itself. You start the work and step back.

Every MCP tool, input, status, error and limit is in [references/tools.md](references/tools.md).

## Connect

The tools come from the Glorya MCP server (`mcp__glorya__*`, `https://platform.glorya.ai/mcp`, signed in with the user's Glorya account). If they are missing, don't search for them, change settings or run any command yourself: signing in opens the user's browser, and `hermes mcp login` drops a working sign-in. Tell the user in one line to run `hermes glorya setup` in their own terminal, then start a new chat.

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
- Publish a landing page or website only when the user says so ("publish it", "make it live"): call `publish_site`. The plugin posts the live link.

## Video styles

Set `format` only if the user named a style. Call `list_video_formats` and pass the matching `id`.

## When something fails

Pass the error message and its link on; don't retry in a loop.

- `plan_required`: share `checkout_url` ($99/month Starter plan).
- `no_credits`: share `billing_url`.
- `setting_up`: the brand is still setting up; try again in a few minutes.
- `limit_reached`: up to 3 jobs run at once per brand. Wait, or stop an ad with `cancel_job`.

## Never

- Launch or change ad campaigns. Glorya can't do that from here.
- Publish a page or site without an explicit ask.

## The user can also type

`/glorya image|video|page|site <brief>`, `/glorya jobs`, `/glorya answer`, `/glorya refine <change>`, `/glorya publish`, `/glorya cancel`. These run without you.
