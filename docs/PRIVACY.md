# Privacy Policy — A.U.R.O.R.A.

Last updated: 15 October 2026

A.U.R.O.R.A. ("Aurora") is open-source software that a person installs and runs on their own computer. There is no
Aurora company, server or cloud service: each installation is operated by the person who installed it (the
"operator"), and the data stays on that computer. This policy describes what the software does with data; the operator
of an installation is responsible for how they use it.

## What Aurora stores, and where

- Conversations, memories, documents and settings are stored on the operator's own computer, in Aurora's folder.
- Keys and tokens for connected services (for example TikTok) are stored in that installation's settings file,
  readable only by Aurora's service account. They are never sent to anyone other than the service they belong to.
- Aurora has no analytics, no advertising, no tracking and no telemetry, and it sells or shares no data.

## TikTok

When the operator connects a TikTok account (TikTok Login Kit and Content Posting API):

- Aurora asks only for the scopes `user.info.basic` and `video.publish`.
- It reads the connected account's basic information (username, display name and the posting options TikTok
  returns for the creator) to show which account is connected and which privacy levels are allowed.
- It uploads to that account only the videos the operator explicitly approves, one by one; every video is declared
  as AI-generated content. Nothing is posted automatically.
- It does not read the account's followers, messages, other videos, or any other user's data.
- The access and refresh tokens are stored locally as described above and used only to call TikTok's API.

## Other cloud services

If the operator chooses to use a cloud language model, the text sent to it is masked first (names, addresses and other
personal data replaced by placeholders); pictures are processed by the local model unless the operator chooses
otherwise.

## Removing data

- Disconnect TikTok at any time in TikTok's settings (Security and permissions → Manage app permissions), and remove
  the token in Aurora's TikTok plugin card.
- Uninstalling Aurora and deleting its folder removes everything it stored.

## Contact

Questions about the software: open an issue on the project's repository,
https://github.com/Soliton0382/A.U.R.O.R.A./issues
