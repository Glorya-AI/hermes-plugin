# Changelog

## 0.1.1

- Ad spend and publishing need your OK: a `pre_tool_call` hook sends every `create_campaign` and `publish_site` call through Hermes' approval prompt, and `/glorya campaign` asks before it starts.
- Downloads check every redirect hop for a public https host, and job ids are made safe before they name a folder.

## 0.1.0

- Follow Glorya jobs in the background: one live progress message, Glorya's questions in the chat, finished videos and images as attachments.
- `/glorya` slash command, `hermes glorya setup|status`, `glorya_attach` and `glorya_jobs` tools, bundled skill.
- Weekly image ads and weekly video ad Automation Blueprints.
- Glorya Studio for Hermes Desktop: studio tab, status-bar chip, inline `::glorya-job` cards.
- Ad campaigns on Meta, Google Ads and TikTok (`/glorya campaign`), plus `/glorya credits`, `/glorya campaigns` and `/glorya sites`.
- Sign-in happens in chat through Hermes' own connection flow; `hermes glorya setup` only writes config and nothing needs a restart.
- `/glorya follow` on a job that finished unfollowed sends its files.
