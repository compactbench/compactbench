# Submission terms

!!! note "Draft"
    These terms take effect when ranked evaluation reopens. Until then they describe how
    the pipeline will treat submissions.

By submitting a method on compactbench.com you agree to the following.

## Your code

- When your run qualifies, your method's source, its pinned requirements and its public
  settings are published in the CompactBench repository under its license (Apache 2.0).
- Submissions are evaluated automatically. The maintainers may remove any submission, or
  bar an account, for abuse or for breaking these terms.

## Your API key

- You supply your own API keys: one for the model your method calls, and an Anthropic key
  for grading (one key can do both if your method uses Anthropic). They are sealed as soon
  as they arrive and opened only inside the evaluation, for the duration of your run.
- You are responsible for your keys' spend limits and for revoking them after the run. The
  proxy stops at a token cap, but your providers bill you for the calls made with them.

## Evaluation outputs

- Your run's scores and metadata (method name and version, model, provider, settings,
  per-family scores, timings and token counts) are published on the leaderboard and in the
  CompactBench repository.
- Full traces — the hidden cases, your method's artifacts at every cycle, and the
  reader's answers — are kept privately by the maintainers. You grant the maintainers a
  perpetual license to keep and use these outputs to operate, audit and improve the
  benchmark, and to publish aggregate or anonymized statistics derived from them.
- The hidden cases are not shared with you. Your own provider may log what your method
  sent it; that is between you and your provider.

## Fair play

- Don't try to recover, fingerprint or store hidden cases, reach anything other than your
  model through the proxy, or tune on hidden results.
- Submissions found doing so are removed, and the submitter may be barred.

## Withdrawal

- You can ask for your row to be removed from the leaderboard at any time. Published pull
  request history and previously released aggregate statistics are not retracted.

Questions: open an issue, or for anything private use [GitHub's private reporting form](https://github.com/compactbench/compactbench/security/advisories/new).
