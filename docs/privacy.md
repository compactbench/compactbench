# Privacy

!!! note "Draft"
    This policy covers the CompactBench repository, the leaderboard site and ranked
    evaluation.

## The site

- The leaderboard is a static site. It has no accounts, no sign-in for visitors, and no
  advertising or tracking cookies.
- Submitting a method needs GitHub sign-in. We read only your public profile (handle and
  id), keep it in a short-lived signed cookie, and never store your GitHub token. We keep
  your handle with your submission, for attribution and rate limits.
- Our hosting provider keeps standard request logs (IP address, user agent, time, page)
  for security and abuse prevention. We use them only in aggregate.
- The contact form sends your message, and your email address if you give one, by email
  to the maintainer. The site doesn't keep a copy. To stop one sender flooding the inbox it
  keeps a keyed hash of your IP address and the time for 24 hours, then deletes it.
- Donations go through Ko-fi, on Ko-fi's own website. We never see your payment details.
- For a daily summary, the site counts a few events in total (sign-ins, new runs, contact
  messages, MCP sessions and tool calls) per day, and reads aggregate traffic figures
  (visitors, page views, countries) from our hosting provider. No visitor, IP address or
  account is recorded for these counts.

## Running CompactBench yourself

- The package makes no network calls of its own. Your runs talk only to the model
  providers you configure, using your keys. Nothing is sent to us.
- Results files hold scores and settings, not conversation text. Traces hold everything
  and stay wherever you write them.

## Ranked submissions

- What a submission publishes, and what is kept privately, is described in the
  [submission terms](submission-terms.md).
- Your API keys are sealed on arrival and opened only inside the evaluation; the plain
  keys are never stored.
- Private traces are encrypted to the maintainers' key before they leave the evaluation
  run, and are kept for auditing and benchmark research.

## Contact

To ask what we hold about you or to have it removed, use the [contact form](https://compactbench.com/contact),
or send the maintainers a private report through
[GitHub's private reporting form](https://github.com/compactbench/compactbench/security/advisories/new).
