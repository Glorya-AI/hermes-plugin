# Glorya tools

The complete Glorya MCP contract: how to connect, every tool with its inputs and results, job statuses, errors and limits. Any MCP client can run Glorya end to end from this page.

## Connection

- Endpoint: `https://platform.glorya.ai/mcp`, streamable HTTP.
- Sign-in: OAuth 2.1 with the user's Glorya account. Discovery starts at `https://platform.glorya.ai/.well-known/oauth-protected-resource/mcp`, which names the authorization server `https://platform.glorya.ai/api/auth`. It supports dynamic client registration, client ID metadata documents and PKCE. Send the access token as `Authorization: Bearer <token>`.
- On sign-in the user picks a default brand. Every tool uses it unless you pass `workspace`.
- Every tool except `get_credits` needs an active Glorya plan on the brand's organization. Work that makes something uses Glorya credits, the same as in the platform. A campaign's ad spend is billed by the ad platform to the user's ad account.

## Read tools

### `list_workspaces`

Finds the account's brands by name, default brand first. Call it only when the user names a brand other than the default.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `query` | string, 1 to 100 characters | optional | none | Part of the brand name the user said. Case and accents don't matter. |
| `limit` | integer, 1 to 50 | optional | `20` | How many brands to return. |

Returns `workspaces` (each with `id`, `name`, `role` `member` or `viewer`, `ready`, `detail`, `is_default`) and a `note` that says when more brands match.

### `get_brand`

The brand as Glorya knows it: name, description, website, language, colors, fonts, logo, and its products. Create tools don't need it; call it when the user asks about their brand or products.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |

Returns `workspace_id`, `brand` (`name`, `description`, `website_url`, `language`, `colors`, `fonts`, `logo_url`) and `products` (each with `id`, `name`, `description`, `key_features`, `price_range`, `primary_cta`, `image_urls`).

### `get_credits`

The brand's plan and credit balance. It works without a plan, so it can tell the user there is none. Call it when the user asks about credits or their plan.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |

Returns `workspace_id`, `plan` (`name` or null, `status` `none`, `active`, `trialing` or `canceled`, `renews_at`, `trial_ends_at`, `cancel_at_period_end`), `credits` (`total`, `subscription`, `topup`, `free`), `billing_url` and `checkout_url` (set only when there is no active plan: the $99/month Starter checkout).

### `get_integrations`

Which ad platforms are connected and which ad account each one uses. `create_campaign` doesn't need it; call it when the user asks what's connected.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |

Returns `workspace_id` and `ad_platforms` (each with `platform` `meta`, `google_ads` or `tiktok`, `connected`, `account` (`id`, `name`, `currency`) or null, and `connect_url`, the page in Glorya to connect it).

### `list_video_formats`

The video styles Glorya can make, with preview clips. Call it when the user asks which styles exist, or to find the `id` of a style the user named.

Annotations: read-only.

No inputs.

Returns `formats` (each with `id`, `name`, `preview_video_url`, `poster_url`).

### `get_job`

A job's current state: status, progress, finished images and videos, open questions with their exact choices, page links, the campaign, and a link to open it in Glorya. With `wait_seconds`, it waits for the job to change before it answers.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_id` | string, 1 to 200 characters | required | none | The `job_id` a create tool or `refine` returned. |
| `wait_seconds` | integer, 0 to 45 | optional | `0` | Use `30`. It returns early as soon as the job changes. |

Returns `job_id`, `kind` (`image_ad`, `video_ad`, `landing_page`, `website` or `campaign`), `status`, `workspace_id`, `open_url`, `next_step`, `title`, `progress` (Glorya's latest message), `error`, `assets` (up to 8, each with `id`, `type`, `url`, `preview_url`, `poster_url`, `width`, `height`, `label`, `created_at`), `questions` (each with `request_id`, `kind`, `question`, `choices`, `details`, `preview_images`), `site` (`kind`, `status`, `preview_url`, `live_url`, `publish_status`, or null for ads and campaigns) and, on campaign jobs once preparation starts, `campaign` (`platform`, `stage`, `daily_budget`, `currency`, `ad_account_id`, `campaign_id`, `manage_url`). Fields may be added over time.

### `list_assets`

Recent images and videos made in the brand, newest first, with a link to the job that made each one.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |
| `type` | string | optional | `"all"` | One of `image`, `video`, `all`. |
| `limit` | integer, 1 to 20 | optional | `10` | How many assets to return. |

Returns `workspace_id` and `assets` (the `get_job` asset fields plus `open_url`).

### `list_sites`

The brand's landing pages and websites, newest first.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |
| `kind` | string | optional | `"all"` | One of `landing_page`, `website`, `all`. |
| `limit` | integer, 1 to 20 | optional | `10` | How many sites to return. |

Returns `workspace_id` and `sites` (each with `id`, `kind`, `name`, `status`, `preview_url`, `live_url`, `updated_at`, `open_url`).

### `list_campaigns`

The brand's ad campaigns with their spend and results.

Annotations: read-only.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `workspace` | string, 1 to 200 characters | optional | none | A brand `id` from `list_workspaces`. Empty means the default brand. |
| `platform` | string | optional | `"all"` | One of `meta`, `google_ads`, `tiktok`, `all`. |
| `status` | string | optional | `"all"` | One of `active`, `paused`, `all`. |
| `days` | integer, 7 or 30 | optional | `30` | Spend and results over the last `7` or `30` days. |
| `limit` | integer, 1 to 20 | optional | `10` | How many campaigns to return. |

Returns `workspace_id`, `range` (`days`, `since`, `until`) and `campaigns`, highest spend first (each with `platform`, `id`, `name`, `status`, `objective`, `daily_budget`, `currency`, `spend`, `impressions`, `clicks`, `results`, `cost_per_result`, `open_url`).

## Create tools

Each starts a job, uses credits and returns `job_id`, `kind`, `status` (`running`), `workspace_id`, `open_url` and `next_step`. Follow the job with `get_job`. Start the job right away from the user's words; Glorya picks the format, size, language and style, and for a campaign the goal and destination, unless the user named them.

### `create_image_ad`

Starts an on-brand image ad.

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `brief` | string, 1 to 4,000 characters | required | none | The user's own words. With no details, pass what they asked for, such as "Create an image ad". |
| `workspace` | string, 1 to 200 characters | optional | none | Set only when the user named another brand. |
| `references` | array of https URLs, up to 8 | optional | `[]` | Only links the user gave. See the reference limits below. |
| `language` | string, two lowercase letters | optional | none | ISO 639-1, such as `en` or `de`. Only when the user said it; the brand's language is used otherwise. |
| `review` | boolean | optional | `false` | Glorya finishes on its own. Set `true` only when the user asks to review or approve steps ("let me review", "show me the concept first"); Glorya then stops for approval at the same steps as in the platform. Never ask the user about it. |

### `create_video_ad`

Starts an on-brand video ad. Rendering takes minutes.

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `brief` | string, 1 to 4,000 characters | required | none | The user's own words. |
| `workspace` | string, 1 to 200 characters | optional | none | Set only when the user named another brand. |
| `references` | array of https URLs, up to 8 | optional | `[]` | Only links the user gave. |
| `language` | string, two lowercase letters | optional | none | Only when the user said it. |
| `review` | boolean | optional | `false` | Glorya finishes on its own. Set `true` only when the user asks to review or approve steps; Glorya then stops at the format, script, start frames and final cut. Never ask the user about it. |
| `format` | string | optional | none | Only when the user named a style. One of `launch_video`, `dont_blink`, `stop_motion`, `mascot_explainer`, `sketch_explainer`, `ugc`, `anime`, `film_noir`, `pixar`, `vox_explainer`, `talking_heads_montage`, `claymation`, `vintage_cartoon`, `stick_figure`, `mannequin`, `fluffy_toy`, `pixel_art`, `podcast`, `high_quality_studio`, `street_interview`, `tv_spot`, `ai_animal`. |

### `create_landing_page`

Starts building an on-brand landing page. It stays unpublished until `publish_site`. Needs at least 100 credits.

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `brief` | string, 1 to 4,000 characters | required | none | The user's own words. |
| `workspace` | string, 1 to 200 characters | optional | none | Set only when the user named another brand. |
| `references` | array of https URLs, up to 8 | optional | `[]` | Only links the user gave. |
| `language` | string, two lowercase letters | optional | none | Only when the user said it. |

### `create_website`

Starts building an on-brand website with several pages. It stays unpublished until `publish_site`. Needs at least 100 credits.

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `brief` | string, 1 to 4,000 characters | required | none | The user's own words. |
| `workspace` | string, 1 to 200 characters | optional | none | Set only when the user named another brand. |
| `references` | array of https URLs, up to 8 | optional | `[]` | Only links the user gave. |
| `language` | string, two lowercase letters | optional | none | Only when the user said it. |

### `create_campaign`

Builds an ad campaign on Meta, Google Ads or TikTok and launches it with real ad spend. By default it runs on its own: Glorya builds the campaign, makes the ads and launches it without asking. With `review: true` it keeps the campaign paused until the user approves the launch. Uses credits; the ad platform bills the ad spend to the user's ad account. Counts against the same job limits.

Annotations: destructive, open world.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `brief` | string, 1 to 4,000 characters | required | none | The user's own words, such as "Get leads for our free trial". |
| `workspace` | string, 1 to 200 characters | optional | none | Set only when the user named another brand. |
| `platform` | string | optional | none | One of `meta`, `google_ads`, `tiktok`. Only when the user named one. Empty means the first connected platform in that order. |
| `goal` | string | optional | none | One of `leads`, `applicants`, `buyers`. Only when the user said it. Empty means Glorya recommends one. |
| `daily_budget` | integer | optional | none | In the ad account's currency. Only when the user gave one. Empty means 30 (TikTok: 50, its minimum). Meta and Google Ads take 10 to 500, TikTok 50 to 500. |
| `destination` | string | optional | none | One of `landing_page`, `instant_form`, `website`. Only when the user said it. Empty means Glorya recommends one. `landing_page`: Glorya builds and publishes a new landing page for the campaign. `instant_form`: Meta only, and not for the `buyers` goal. `website`: needs `website_url`. |
| `website_url` | string, up to 2,048 characters | optional | none | The page the ads link to when `destination` is `website`. |
| `references` | array of https URLs, up to 8 | optional | `[]` | Only links the user gave; Glorya uses them as the ad creatives. Empty means Glorya makes them. |
| `language` | string, two lowercase letters | optional | none | Only when the user said it. |
| `review` | boolean | optional | `false` | Glorya builds and launches on its own. Set `true` only when the user asks to review or approve ("let me review the campaign first"); Glorya then keeps it paused until the user approves the launch. Never ask the user about it. |

In `get_job`, `campaign` appears once Glorya starts preparing: `platform`, `stage` (`planning`, `preparing`, `ready`, `incomplete` or `cancelled`), `daily_budget`, `currency`, `ad_account_id`, `campaign_id` (when known) and `manage_url`. For the live status, spend and results after launch, call `list_campaigns`.

## Act tools

### `respond`

Sends the user's answer to a question Glorya asked (`get_job` status `needs_input`).

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_id` | string, 1 to 200 characters | required | none | The job with the open question. |
| `answer` | string, 1 to 4,000 characters | required | none | For `decision` and `approve` questions, one exact label from `choices`. For `input`, `revise` and `clarify`, the user's own words. |
| `request_id` | string, 1 to 200 characters | optional | none | The question's `request_id`. Needed when more than one question is open. |

Returns `job_id`, `request_id`, `answer`, `status` (`submitted`) and `next_step`.

### `refine`

Asks Glorya to change a job's result: new copy, another variation, a different color, a page edit, a campaign change. Uses credits; page edits need at least 100.

Annotations: writes, not destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_id` | string, 1 to 200 characters | required | none | The job to change. |
| `instruction` | string, 1 to 4,000 characters | required | none | What to change, in the user's words. |
| `review` | boolean | optional | `false` | Image ads, video ads and campaigns only. Glorya finishes on its own. Set `true` only when the user asks to review or approve steps. Never ask the user about it. |

Returns the same fields as a create tool. Follow the same `job_id` with `get_job`.

### `publish_site`

Puts a finished landing page or website live on the internet. Call it only when the user explicitly asks to publish.

Annotations: destructive, open world.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_id` | string, 1 to 200 characters | required | none | A completed landing page or website job. |
| `slug` | string, up to 63 characters | optional | none | Subdomain: lowercase letters, digits and dashes, not starting or ending with a dash. Empty keeps the current or default one. |

Returns `job_id`, `status` (`publishing`), `open_url` and `next_step`. Then call `get_job` until `site.live_url` is set.

### `cancel_job`

Stops a running image ad, video ad or campaign job and closes its open question. Finished files stay in Glorya. A campaign that's already live keeps running; the user pauses it in Glorya or the ad platform. Landing page and website builds can't be cancelled.

Annotations: destructive.

| Input | Type | Required | Default | Notes |
| --- | --- | --- | --- | --- |
| `job_id` | string, 1 to 200 characters | required | none | The job to stop. |

Returns `job_id`, `status` (`cancelling`, or `nothing_running`) and `next_step`.

## Job status

| Status | What to do |
| --- | --- |
| `running` | Call `get_job` again with `wait_seconds` 30. Tell the user now and then that it is still working. |
| `needs_input` | Show each item in `questions` as written, with its exact `choices` and `preview_images`. Send the user's answer with `respond`, then keep following the job. |
| `completed` | Share the results: each asset `url`, `site.preview_url` and `site.live_url` for pages, or `campaign.manage_url` for campaigns (then `list_campaigns` for its live status), plus `open_url`. If `progress` asks the user something, relay it and send the answer with `refine`. |
| `failed` | Tell the user what `error` or `progress` says. Offer `refine` with a changed instruction, or a new job. |
| `cancelled` | The job stopped. Finished files stay in Glorya, and a live campaign keeps running. |

Question kinds: `decision` and `approve` take one exact label from `choices`; `input`, `revise` and `clarify` also take the user's own words.

## Errors

A failed call returns `isError: true` with a message for the user and a JSON object with `error` (the code) and details such as links. Relay the message and its link. Don't retry in a loop.

| Code | Meaning | What to do |
| --- | --- | --- |
| `plan_required` | The brand's organization has no active plan. | Share `checkout_url` ($99/month Starter). Try again after the user starts it. |
| `no_credits` | Not enough credits. | Share `billing_url` so the user can top up. |
| `setting_up` | The brand is still setting up. | Try again in a few minutes. Share `open_url`. |
| `available_shortly` | This feature isn't ready for this brand from AI apps yet (its agent is being updated). | Suggest Glorya in the browser (`open_url`). Landing pages and websites work. |
| `agent_unavailable` | The brand's agent is unavailable or updating. | Try again in a minute, or open Glorya. |
| `integration_required` | The ad platform isn't connected or has no ad account selected. | Share `connect_url`; `platform` and `connected_platforms` say what is connected. Then try again. |
| `workspace_required` | No default brand and several brands. | Ask which brand, or find it with `list_workspaces` and `query`. Pass its `id` as `workspace`. |
| `workspace_not_found` | The `workspace` id isn't one of the user's brands. | Call `list_workspaces` with `query` set to the brand the user named. |
| `view_only` | The account can only view this brand. | Tell the user; they can't create for it. |
| `limit_reached` | Too many jobs running or started. | Wait for a job to finish, or stop an image ad, video ad or campaign job with `cancel_job`. |
| `rate_limited` | `get_job` was called too often. | Wait `retry_after_seconds`, then poll with `wait_seconds` 30. |
| `invalid_reference` | A reference link can't be used. | Ask for a public https link within the limits below. |
| `invalid_budget` | `daily_budget` is outside the platform's range. | Ask for a budget between `min` and `max` (in `currency`). |
| `invalid_destination` | The destination doesn't fit: `instant_form` is Meta only and not for buyers, `website` needs `website_url`. | Change the destination or pass `website_url`. |
| `job_not_found` | No job with that id for this account. | Check the `job_id`. |
| `no_open_question` | The question was answered, expired, or `request_id` is needed. | Call `get_job` for the current questions. |
| `invalid_answer` | The answer isn't one of the exact choices. | Send one label from `choices`. |
| `not_publishable` | Not a site, still building, waiting for an answer, or already publishing. | Wait for `completed`, then publish. |
| `not_cancellable` | Landing page and website builds can't be cancelled. | Use `refine` to change the result instead. |
| `upstream_error` | Glorya couldn't do the action. | Tell the user the message. |
| `internal_error` | An unexpected error. | Try again in a moment. |

## Limits

- Jobs running at once: 3 per brand, 10 per organization. Campaigns and changes with `refine` count.
- New jobs: 30 per hour per person.
- `get_job`: 120 calls a minute per person. Use `wait_seconds` instead of a tight loop.
- `brief`, `instruction` and `answer`: up to 4,000 characters.
- `references`: public https links only, checked by their bytes. Up to 6 JPG, PNG or WebP images (20 MB and 4,096 px a side each) and 2 MP4 or MOV videos (200 MB and 2 minutes each), 250 MB per call, all downloaded within 40 seconds.
- `list_assets`, `list_sites` and `list_campaigns`: up to 20 per call. `get_job`: up to 8 assets per job.
- `daily_budget`: 10 to 500 on Meta and Google Ads, 50 to 500 on TikTok, in the ad account's currency.
- Landing pages and websites need at least 100 credits to start, continue or change.

## Prompts

The server also offers four prompts without arguments: `image-ad`, `video-ad`, `landing-page` and `website` (in Claude Code, `/glorya:image-ad` and so on). Each starts that job right away.
