"""Vocabulary the scenario engine draws from.

Everything a generated conversation mentions — people, projects, components,
rules, decision topics — comes from a :class:`Lexicon`. The public lexicon
below drives the Starter and Practice suites. Ranked suites use private
lexicons with the same shape, so a method can't win by memorising the public
word lists.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RuleTemplate:
    """A rule a conversation can establish.

    ``label`` is the canonical short form shown as an answer option. ``direct``
    and ``indirect`` are ways of stating it in the conversation. ``violation``
    and ``compliant`` are concrete next steps that break / respect it. Strings
    may contain ``{n}`` (replaced by one of ``values``) and ``{project}``.
    """

    key: str
    label: str
    direct: tuple[str, ...]
    indirect: tuple[str, ...]
    violation: str
    compliant: str
    values: tuple[str, ...] = ()
    value_question: str = ""
    value_kind: str = "number"


@dataclass(frozen=True)
class DecisionTopic:
    """Something a team decides, possibly several times."""

    key: str
    label: str
    question: str
    options: tuple[str, ...]
    value_kind: str = "text"


@dataclass(frozen=True)
class FactTemplate:
    """An exact value a conversation can establish (and later correct).

    ``kind`` is ``money``, ``number``, ``date``, ``version`` or ``ident``. Values are
    drawn from ``choices`` when given, else from ``low``..``high`` (for ``date``,
    days after 2026-01-01; for ``ident``, the digits after ``prefix``).
    ``statements`` use ``{project}`` and ``{value}``.
    """

    key: str
    label: str
    question: str
    kind: str
    statements: tuple[str, ...]
    low: int = 0
    high: int = 0
    choices: tuple[str, ...] = ()
    prefix: str = ""


@dataclass(frozen=True)
class ScopedPolicy:
    """A rule that covers only some components, possibly until a date.

    ``statements`` use ``{project}``, ``{targets}`` (a list of components) and
    ``{date}`` when ``dated``.
    """

    key: str
    label: str
    statements: tuple[str, ...]
    dated: bool = False


@dataclass(frozen=True)
class Lexicon:
    first_names: tuple[str, ...]
    last_names: tuple[str, ...]
    lookalike_last_names: tuple[tuple[str, ...], ...]
    roles: tuple[str, ...]
    orgs: tuple[str, ...]
    projects: tuple[str, ...]
    components: tuple[str, ...]
    rules: tuple[RuleTemplate, ...]
    topics: tuple[DecisionTopic, ...]
    vendors: tuple[str, ...]
    open_questions: tuple[str, ...]
    function_verbs: tuple[str, ...] = field(default=())
    function_nouns: tuple[str, ...] = field(default=())
    endpoints: tuple[str, ...] = field(default=())
    ticket_prefixes: tuple[str, ...] = field(default=())
    facts: tuple[FactTemplate, ...] = field(default=())
    task_titles: tuple[str, ...] = field(default=())
    """Ticket titles; may use ``{component}``."""
    scoped_policies: tuple[ScopedPolicy, ...] = field(default=())
    phrases: Mapping[str, tuple[str, ...]] = field(default_factory=dict[str, tuple[str, ...]])
    """Overrides for the sentence templates families use, keyed like ``"decision.initial"``.

    Every template a family speaks with has a public default; a private lexicon
    replaces them so ranked cases can't be picked apart by matching public wording.
    """


_RULES: tuple[RuleTemplate, ...] = (
    RuleTemplate(
        key="friday_deploys",
        label="No production deploys on Fridays",
        direct=("Hard rule for {project}: nothing goes to production on a Friday.",),
        indirect=(
            "After what happened last quarter, Friday releases are off the table for {project}.",
            "Ops asked that we stop pushing {project} to prod at the end of the week — Fridays are out.",
        ),
        violation="Ship the release to production on Friday afternoon so it's out before the weekend",
        compliant="Ship the release to production on Tuesday morning",
    ),
    RuleTemplate(
        key="pii_logs",
        label="Never write customer PII to application logs",
        direct=(
            "Never log customer PII anywhere in {project} — no emails, names or addresses in logs.",
        ),
        indirect=(
            "Legal flagged the log pipeline: customer emails and addresses can't end up in {project}'s logs.",
        ),
        violation="Add the customer's email address to the request log line to make debugging easier",
        compliant="Log the hashed customer ID instead of the email address",
    ),
    RuleTemplate(
        key="eu_data",
        label="Customer data stays in EU regions",
        direct=("All {project} customer data must stay in EU regions.",),
        indirect=(
            "The contract we signed means {project}'s customer records can't leave the EU — keep that in mind for every storage choice.",
        ),
        violation="Replicate the customer table to us-east-1 for lower read latency",
        compliant="Add a read replica in eu-central-1",
    ),
    RuleTemplate(
        key="batch_size",
        label="Export batches stay under the row limit",
        direct=("Export batches for {project} are capped at {n} rows per file.",),
        indirect=(
            "The downstream importer chokes on anything past {n} rows a file, so {project}'s export files are capped at {n} rows.",
        ),
        violation="Write the whole multi-million-row export as one file to keep the pipeline simple",
        compliant="Split the export into files below the row limit",
        values=("5000", "8000", "10000", "25000", "50000"),
        value_question="What is the per-file row cap for {project}'s export batches?",
    ),
    RuleTemplate(
        key="review_required",
        label="Every change to main needs an approving review",
        direct=("Nothing merges into {project}'s main branch without an approving review.",),
        indirect=(
            "Security wants a second pair of eyes on everything that lands on {project}'s main branch — no self-merges.",
        ),
        violation="Merge the hotfix straight to main without waiting for a review",
        compliant="Open a pull request and get an approving review before merging",
    ),
    RuleTemplate(
        key="no_new_deps",
        label="No new third-party dependencies without approval",
        direct=("Don't add any new third-party packages to {project} without sign-off.",),
        indirect=(
            "We're in the middle of a supply-chain audit, so {project} doesn't get new third-party packages unless they're signed off first.",
        ),
        violation="Pull in a new open-source date-parsing library to fix the timezone bug",
        compliant="Fix the timezone bug with the standard library",
    ),
    RuleTemplate(
        key="api_timeout",
        label="Outbound API calls time out within the limit",
        direct=("Every outbound HTTP call in {project} needs a timeout of at most {n} seconds.",),
        indirect=(
            "After the outage, the rule became that {project} never waits on a partner API longer than {n} seconds.",
        ),
        violation="Remove the timeout on the partner API call so slow responses still succeed",
        compliant="Keep the partner API call's timeout within the limit and retry with backoff",
        values=("2", "3", "5", "8", "10"),
        value_question="What is the maximum timeout, in seconds, for outbound HTTP calls in {project}?",
    ),
    RuleTemplate(
        key="feature_flags",
        label="New features ship behind a feature flag",
        direct=("Every new {project} feature ships behind a feature flag.",),
        indirect=(
            "Product wants to be able to turn anything new in {project} off without a deploy, so it all goes out flagged.",
        ),
        violation="Release the new checkout page to everyone directly, without a flag",
        compliant="Release the new checkout page behind a flag at 5%",
    ),
    RuleTemplate(
        key="no_prod_data_in_staging",
        label="Production data is never copied into staging",
        direct=("Production data never gets copied into the {project} staging environment.",),
        indirect=(
            "The auditors were clear that staging for {project} only ever sees synthetic data.",
        ),
        violation="Restore last night's production snapshot into staging to reproduce the bug",
        compliant="Generate a synthetic dataset that reproduces the bug in staging",
    ),
    RuleTemplate(
        key="spend_cap",
        label="Cloud spend stays under the monthly cap",
        direct=("{project}'s cloud spend has a hard cap of ${n} a month.",),
        indirect=(
            "Finance only approved ${n} a month for {project}'s infrastructure, and they meant it.",
        ),
        violation="Leave a load-test cluster running all month that on its own costs more than the monthly cap",
        compliant="Run the load test on a temporary cluster and tear it down afterwards",
        values=("4000", "6500", "9000", "12000", "15000"),
        value_question="What is {project}'s monthly cloud spend cap in dollars?",
        value_kind="money",
    ),
    RuleTemplate(
        key="password_hashing",
        label="Passwords are hashed with argon2 only",
        direct=("{project} hashes passwords with argon2 — nothing else.",),
        indirect=(
            "The security review settled it: argon2 is the only acceptable password hash in {project}.",
        ),
        violation="Hash the migrated passwords with SHA-256 to speed up the import",
        compliant="Re-hash the migrated passwords with argon2 on next login",
    ),
    RuleTemplate(
        key="customer_comms",
        label="No customer-facing email without support sign-off",
        direct=(
            "No customer-facing email goes out from {project} without support signing off first.",
        ),
        indirect=(
            "Support got burned by the last surprise announcement — anything {project} emails to customers goes past them first.",
        ),
        violation="Send the maintenance notice to all customers tonight without running it past support",
        compliant="Send the maintenance notice draft to support for sign-off",
    ),
    RuleTemplate(
        key="change_freeze",
        label="No schema changes during the change freeze",
        direct=("{project} is in a change freeze: no database schema changes until it ends.",),
        indirect=(
            "With the audit window open, the database schema for {project} stays exactly as it is.",
        ),
        violation="Add a new column to the orders table this week",
        compliant="Queue the new column for after the freeze ends",
    ),
    RuleTemplate(
        key="max_retries",
        label="Retries are capped",
        direct=(
            "Background jobs in {project} retry at most {n} times before going to the dead-letter queue.",
        ),
        indirect=(
            "We agreed that a failing {project} job gets {n} retries, tops, then it's parked in the dead-letter queue.",
        ),
        violation="Set the job to retry forever until it succeeds",
        compliant="Cap the job's retries and route failures to the dead-letter queue",
        values=("3", "4", "5", "6"),
        value_question="How many times may a failing background job in {project} retry?",
    ),
    RuleTemplate(
        key="no_force_push",
        label="No force-pushes to shared branches",
        direct=("Never force-push to a shared {project} branch.",),
        indirect=(
            "After the history rewrite incident, {project}'s shared branches are strictly append-only.",
        ),
        violation="Force-push the rebased branch over the shared release branch",
        compliant="Merge main into the release branch instead of rebasing it",
    ),
    RuleTemplate(
        key="mobile_min_version",
        label="Support the minimum OS version",
        direct=("{project} must keep working on iOS {n} and later.",),
        indirect=("A big chunk of {project}'s users are still on iOS {n}, so we can't drop it.",),
        violation="Adopt an API that only exists on the newest iOS release without a fallback",
        compliant="Use the new API behind an availability check with a fallback",
        values=("15", "16", "17"),
        value_question="What is the oldest iOS version {project} must support?",
    ),
    RuleTemplate(
        key="secrets_manager",
        label="Secrets live only in the secrets manager",
        direct=(
            "{project}'s secrets live in the secrets manager and nowhere else — not in env files, not in CI variables.",
        ),
        indirect=(
            "Since the leaked token, every {project} credential gets pulled from the secrets manager at runtime.",
        ),
        violation="Put the new API key in the CI pipeline's environment variables",
        compliant="Store the new API key in the secrets manager and read it at runtime",
    ),
    RuleTemplate(
        key="on_call_hours",
        label="Risky changes only during on-call hours",
        direct=(
            "Risky {project} changes only go out between 09:00 and {n}:00 UTC, when on-call is staffed.",
        ),
        indirect=(
            "On-call for {project} is only staffed until {n}:00 UTC, so nothing risky ships after that.",
        ),
        violation="Roll out the new load balancer config at 23:00 UTC when traffic is lowest",
        compliant="Roll out the new load balancer config mid-morning UTC while on-call is staffed",
        values=("15", "16", "17", "18"),
        value_question="Up to what hour UTC (24-hour clock, just the hour) may risky {project} changes go out?",
    ),
    RuleTemplate(
        key="restore_tests",
        label="Backups are restore-tested every month",
        direct=("{project}'s backups get a full restore test every month.",),
        indirect=(
            "A backup nobody has restored doesn't count, so {project} restore-tests monthly.",
        ),
        violation="Skip this month's restore test because last night's backup finished fine",
        compliant="Run this month's restore test into a scratch environment",
    ),
    RuleTemplate(
        key="no_copyleft",
        label="No copyleft dependencies",
        direct=("{project} can't ship copyleft-licensed dependencies.",),
        indirect=("Legal ruled out GPL-style licenses anywhere in {project}'s shipped code.",),
        violation="Paste a GPL-licensed code snippet into the shipped product",
        compliant="Write the helper from scratch instead of pasting GPL code",
    ),
    RuleTemplate(
        key="accessibility",
        label="New UI meets the accessibility checklist",
        direct=("Every new {project} screen passes the accessibility checklist before release.",),
        indirect=(
            "After the audit, {project} doesn't ship screens that fail keyboard and screen-reader checks.",
        ),
        violation="Ship the new settings page without keyboard navigation",
        compliant="Add keyboard navigation and labels before shipping the settings page",
    ),
    RuleTemplate(
        key="purge_window",
        label="Deleted accounts are purged within the window",
        direct=("{project} purges a deleted account's data within {n} days.",),
        indirect=("Privacy committed {project} to wiping deleted accounts inside {n} days.",),
        violation="Keep deleted accounts' data indefinitely in case they come back",
        compliant="Purge deleted accounts with the scheduled job inside the window",
        values=("7", "14", "30", "45"),
        value_question="Within how many days must {project} purge a deleted account's data?",
    ),
    RuleTemplate(
        key="two_person_prod",
        label="Production database access needs a second person",
        direct=(
            "Nobody touches {project}'s production database alone; a second engineer watches.",
        ),
        indirect=("{project} runs production database work in pairs, always.",),
        violation="Run the one-off fix query against the production database alone",
        compliant="Pair with a second engineer to run the fix query",
    ),
    RuleTemplate(
        key="no_debug_logs",
        label="No debug logging in production",
        direct=("Debug-level logging stays off in {project} production.",),
        indirect=(
            "The last debug-logging spike cost a fortune, so {project} prod logs at info and up.",
        ),
        violation="Turn on debug logging in production to chase the bug",
        compliant="Reproduce the bug in staging with debug logging on",
    ),
    RuleTemplate(
        key="vendor_review",
        label="New vendors pass a security review first",
        direct=("No new vendor gets {project} data before passing a security review.",),
        indirect=("Security has to clear any vendor before {project} sends it a single record.",),
        violation="Sign up for a new analytics vendor today and start sending it user events",
        compliant="Send the analytics vendor through the security review first",
    ),
    RuleTemplate(
        key="localized_copy",
        label="Customer-facing copy goes through localization",
        direct=("All customer-facing text in {project} goes through the localization files.",),
        indirect=("{project} ships in nine languages, so no user-visible string is hard-coded.",),
        violation="Hard-code English error messages in the new checkout flow",
        compliant="Add the new error messages to the localization files",
    ),
)

_TOPICS: tuple[DecisionTopic, ...] = (
    DecisionTopic(
        "database",
        "primary database",
        "Which primary database does {project} use?",
        ("Postgres", "MySQL", "CockroachDB", "DynamoDB", "MongoDB", "SQL Server"),
    ),
    DecisionTopic(
        "queue",
        "message queue",
        "Which message queue does {project} use?",
        ("Kafka", "RabbitMQ", "Amazon SQS", "NATS", "Redis Streams", "Google Pub/Sub"),
    ),
    DecisionTopic(
        "region",
        "primary hosting region",
        "Which region is {project} primarily hosted in?",
        ("us-east-1", "us-west-2", "eu-west-1", "eu-central-1", "ap-southeast-2", "ca-central-1"),
    ),
    DecisionTopic(
        "ci",
        "CI provider",
        "Which CI provider does {project} use?",
        ("GitHub Actions", "CircleCI", "Buildkite", "GitLab CI", "Jenkins"),
    ),
    DecisionTopic(
        "frontend",
        "frontend framework",
        "Which frontend framework is {project} built with?",
        ("React", "Svelte", "Vue", "Angular", "SolidJS"),
    ),
    DecisionTopic(
        "payments",
        "payment processor",
        "Which payment processor does {project} use?",
        ("Stripe", "Adyen", "Braintree", "Checkout.com", "PayPal"),
    ),
    DecisionTopic(
        "email",
        "transactional email provider",
        "Which transactional email provider does {project} use?",
        ("Postmark", "SendGrid", "Mailgun", "Amazon SES", "Resend"),
    ),
    DecisionTopic(
        "observability",
        "observability stack",
        "Which observability stack does {project} use?",
        ("Datadog", "Grafana Cloud", "Honeycomb", "New Relic", "Elastic APM"),
    ),
    DecisionTopic(
        "auth",
        "identity provider",
        "Which identity provider does {project} use?",
        ("Auth0", "Okta", "Clerk", "Keycloak", "Amazon Cognito"),
    ),
    DecisionTopic(
        "search",
        "search engine",
        "Which search engine powers {project}'s search?",
        ("Elasticsearch", "OpenSearch", "Meilisearch", "Typesense", "Algolia"),
    ),
    DecisionTopic(
        "rollout",
        "rollout strategy",
        "What rollout strategy is {project} using for the launch?",
        (
            "a 5% canary",
            "blue-green deployment",
            "a dark launch behind a flag",
            "a big-bang cutover",
            "region-by-region rollout",
        ),
    ),
    DecisionTopic(
        "api_style",
        "public API style",
        "What style is {project}'s public API?",
        ("REST", "GraphQL", "gRPC", "JSON-RPC"),
    ),
    DecisionTopic(
        "warehouse",
        "data warehouse",
        "Which data warehouse does {project} report from?",
        ("Snowflake", "BigQuery", "Redshift", "ClickHouse", "Databricks"),
    ),
    DecisionTopic(
        "launch_date",
        "launch date",
        "What is {project}'s launch date?",
        (
            "2026-03-02",
            "2026-03-16",
            "2026-03-30",
            "2026-04-13",
            "2026-04-27",
            "2026-05-11",
        ),
        value_kind="date",
    ),
    DecisionTopic(
        "budget",
        "approved budget",
        "What is {project}'s approved budget?",
        ("$48,000", "$62,500", "$75,000", "$90,000", "$118,000", "$140,000"),
        value_kind="money",
    ),
    DecisionTopic(
        "target_version",
        "target release version",
        "Which release version is {project} targeting?",
        ("v2.4.0", "v2.5.0", "v2.6.1", "v3.0.0", "v3.1.0"),
        value_kind="version",
    ),
    DecisionTopic(
        "cache",
        "cache layer",
        "Which cache layer does {project} use?",
        ("Redis", "Memcached", "Valkey", "Dragonfly", "KeyDB"),
    ),
    DecisionTopic(
        "flags",
        "feature-flag tool",
        "Which feature-flag tool does {project} use?",
        ("LaunchDarkly", "Unleash", "Flagsmith", "GrowthBook", "ConfigCat"),
    ),
    DecisionTopic(
        "errors",
        "error tracker",
        "Which error tracker does {project} use?",
        ("Sentry", "Rollbar", "Bugsnag", "Honeybadger", "Raygun"),
    ),
    DecisionTopic(
        "docs",
        "docs platform",
        "Which docs platform hosts {project}'s documentation?",
        ("Docusaurus", "MkDocs", "GitBook", "Mintlify", "ReadMe"),
    ),
    DecisionTopic(
        "ui_kit",
        "component library",
        "Which component library is {project}'s UI built on?",
        ("Radix", "MUI", "Chakra UI", "Mantine", "shadcn/ui"),
    ),
    DecisionTopic(
        "load_test",
        "load-testing tool",
        "Which load-testing tool does {project} use?",
        ("k6", "Locust", "Gatling", "JMeter", "Artillery"),
    ),
    DecisionTopic(
        "status",
        "status page provider",
        "Which status page provider does {project} use?",
        ("Statuspage", "Instatus", "Better Stack", "Cachet", "Status.io"),
    ),
    DecisionTopic(
        "analytics",
        "product analytics tool",
        "Which product analytics tool does {project} use?",
        ("Amplitude", "Mixpanel", "PostHog", "Heap", "Pendo"),
    ),
    DecisionTopic(
        "web_hosting",
        "frontend hosting",
        "Where is {project}'s frontend hosted?",
        ("Vercel", "Netlify", "Cloudflare Pages", "Render", "Fly.io"),
    ),
)

PUBLIC_LEXICON = Lexicon(
    first_names=(
        "Priya",
        "Marcus",
        "Dana",
        "Sam",
        "Elena",
        "Tomás",
        "Aisha",
        "Jonah",
        "Mei",
        "Viktor",
        "Grace",
        "Omar",
        "Lena",
        "Diego",
        "Hana",
        "Felix",
        "Ruth",
        "Kenji",
        "Amara",
        "Nils",
        "Sofia",
        "Malik",
        "Ingrid",
        "Ravi",
        "Chloe",
        "Andrés",
        "Zara",
        "Tobias",
        "Yuki",
        "Bea",
        "Caleb",
        "Nadia",
        "Oskar",
        "Leila",
        "Mateo",
        "Freya",
        "Idris",
        "Clara",
        "Hugo",
        "Asha",
        "Rafael",
        "Maya",
        "Jonas",
        "Esther",
        "Kofi",
        "Lucía",
        "Arjun",
        "Nora",
        "Emil",
        "Tessa",
    ),
    last_names=(
        "Raman",
        "Lindgren",
        "Okafor",
        "Castellanos",
        "Brandt",
        "Nakamura",
        "Haddad",
        "Petrov",
        "Abara",
        "Sørensen",
        "Mendes",
        "Kaur",
        "Fischer",
        "Adeyemi",
        "Duarte",
        "Kim",
        "Volkov",
        "Ferreira",
        "Oyelaran",
        "Bauer",
        "Takahashi",
        "Gallo",
        "Iqbal",
        "Novotný",
        "Achebe",
        "Ruiz",
        "Holm",
        "Moreau",
        "Chen",
        "Kapoor",
        "Lund",
        "Esposito",
        "Mwangi",
        "Varga",
    ),
    # Each group shares a first name in the cast; surnames differ by at least two
    # edits, so they confuse a lossy summary without confusing a careful reader.
    lookalike_last_names=(
        ("Whitfield", "Whitaker", "Whitman"),
        ("Ortiz", "Ortega", "Orta"),
        ("Hansen", "Hanley", "Hanlon"),
        ("Lindqvist", "Lindgren", "Lindholm"),
        ("Moreno", "Marino", "Morales"),
        ("Kowalski", "Kowalczyk", "Kowal"),
        ("Brennan", "Brannon", "Brenner"),
        ("Castillo", "Castro", "Castellanos"),
        ("Novak", "Novotny", "Nolan"),
        ("Reyes", "Reese", "Reyna"),
        ("Andersen", "Andrews", "Anders"),
        ("Becker", "Baker", "Bowers"),
    ),
    roles=(
        "staff engineer",
        "engineering manager",
        "product manager",
        "designer",
        "security lead",
        "site reliability engineer",
        "data engineer",
        "QA lead",
        "finance partner",
        "legal counsel",
        "support lead",
        "solutions architect",
        "platform engineer",
        "mobile engineer",
        "head of operations",
    ),
    orgs=(
        "Northwind Labs",
        "Contoso Group",
        "Fabrikam Systems",
        "Tailspin Digital",
        "Wingtip Partners",
        "Litware Consulting",
        "Proseware Inc.",
        "Adatum Corp",
        "Lucerne Analytics",
        "Margie's Logistics",
        "Coho Ventures",
        "Blue Yonder Tech",
        "Alpine Ridge Software",
        "Graphic Designs Co.",
        "Humongous Insurance",
        "Trey Research",
    ),
    projects=(
        "Atlas",
        "Juniper",
        "Halcyon",
        "Kestrel",
        "Meridian",
        "Larkspur",
        "Obsidian",
        "Tundra",
        "Beacon",
        "Cobalt",
        "Ember",
        "Fjord",
        "Granite",
        "Helix",
        "Ironwood",
        "Lantern",
        "Marlin",
        "Nimbus",
        "Orchid",
        "Pioneer",
        "Quartz",
        "Redwood",
        "Sable",
        "Tidal",
        "Umber",
        "Vesper",
    ),
    components=(
        "billing service",
        "auth gateway",
        "nightly export job",
        "search indexer",
        "notification worker",
        "admin dashboard",
        "mobile app",
        "payments webhook handler",
        "warehouse sync",
        "feature-flag service",
        "rate limiter",
        "audit log pipeline",
        "onboarding flow",
        "invoice generator",
        "public API",
        "reporting service",
        "image resizer",
        "session store",
        "CSV importer",
        "recommendation engine",
    ),
    rules=_RULES,
    topics=_TOPICS,
    vendors=(
        "Altavera",
        "Brightloom",
        "Cindervale",
        "Driftwell",
        "Emberstack",
        "Fernhollow",
        "Halverd",
        "Ironleaf",
        "Junoport",
        "Lumenfold",
        "Moorgate",
        "Northpass",
        "Oakhaven",
        "Quillmark",
        "Rookwood",
        "Silverbirch",
    ),
    open_questions=(
        "requiring two reviewers on every pull request",
        "moving the standup to the afternoon",
        "dropping support for the legacy v1 API",
        "adding a staging soak period before releases",
        "switching the on-call rotation to weekly",
        "paying for a dedicated load-testing environment",
        "rewriting the importer in Rust",
        "offering a self-hosted edition",
    ),
    function_verbs=(
        "build",
        "load",
        "sync",
        "resolve",
        "parse",
        "flush",
        "retry",
        "render",
        "validate",
        "enqueue",
        "reconcile",
        "normalize",
        "hydrate",
        "dispatch",
        "compute",
        "fetch",
    ),
    function_nouns=(
        "invoice",
        "session",
        "batch",
        "token",
        "payload",
        "cursor",
        "manifest",
        "ledger",
        "snapshot",
        "webhook",
        "quota",
        "schedule",
        "report",
        "profile",
        "export",
        "receipt",
    ),
    endpoints=(
        "/v2/orders",
        "/v2/invoices",
        "/v2/customers",
        "/v2/exports",
        "/v2/sessions",
        "/v2/webhooks",
        "/v2/reports",
        "/v2/search",
        "/v2/usage",
        "/v2/plans",
    ),
    ticket_prefixes=("OPS", "ENG", "SEC", "DATA", "MOB", "PAY"),
    facts=(
        FactTemplate(
            "downtime_allowance",
            "monthly downtime allowance",
            "How many minutes of downtime a month does {project}'s SLA allow?",
            "number",
            ("{project}'s SLA allows {value} minutes of downtime a month.",),
            choices=("22", "43", "65", "108", "216"),
        ),
        FactTemplate(
            "pentest_date",
            "penetration test date",
            "When is {project}'s penetration test booked?",
            "date",
            ("{project}'s penetration test is booked for {value}.",),
            low=90,
            high=400,
        ),
        FactTemplate(
            "contract_value",
            "signed contract value",
            "What is {project}'s signed contract value?",
            "money",
            (
                "The signed contract value for {project} is {value}.",
                "Procurement closed {project}'s contract at {value}.",
            ),
            low=20_000,
            high=250_000,
        ),
        FactTemplate(
            "purchase_order",
            "purchase order number",
            "What is {project}'s purchase order number?",
            "ident",
            (
                "The purchase order for {project} is {value}.",
                "Use PO {value} for anything billed to {project}.",
            ),
            low=100_000,
            high=999_999,
            prefix="PO-",
        ),
        FactTemplate(
            "uptime_target",
            "uptime target",
            "What uptime target (percent) has {project} committed to?",
            "number",
            (
                "{project} is committing to {value}% uptime.",
                "The SLA we signed for {project} says {value}% availability.",
            ),
            choices=("99.5", "99.9", "99.95", "99.99"),
        ),
        FactTemplate(
            "rate_limit",
            "public API rate limit",
            "What is the rate limit, in requests per minute, on {project}'s public API?",
            "number",
            ("{project}'s public API is limited to {value} requests per minute.",),
            low=300,
            high=6_000,
        ),
        FactTemplate(
            "log_retention",
            "audit log retention",
            "How many days are {project}'s audit logs kept?",
            "number",
            (
                "Audit logs for {project} are kept for {value} days.",
                "We retain {project}'s audit trail for {value} days.",
            ),
            choices=("30", "45", "60", "90", "180", "365", "400"),
        ),
        FactTemplate(
            "go_live",
            "go-live date",
            "What is {project}'s go-live date?",
            "date",
            ("{project} goes live on {value}.", "Go-live for {project} is set for {value}."),
            low=150,
            high=500,
        ),
        FactTemplate(
            "support_renewal",
            "support contract renewal date",
            "When does {project}'s support contract renew?",
            "date",
            ("The support contract for {project} renews on {value}.",),
            low=100,
            high=600,
        ),
        FactTemplate(
            "sdk_pin",
            "pinned client SDK version",
            "Which client SDK version is {project} pinned to?",
            "version",
            (
                "{project} is pinned to {value} of the client SDK.",
                "Keep {project} on SDK {value} for now.",
            ),
            choices=("v4.2.1", "v4.3.0", "v4.3.2", "v5.0.0", "v5.1.4", "v5.2.0"),
        ),
        FactTemplate(
            "headcount",
            "engineering headcount",
            "How many engineers are allocated to {project} this quarter?",
            "number",
            ("{project} has {value} engineers allocated this quarter.",),
            low=3,
            high=40,
        ),
        FactTemplate(
            "payload_cap",
            "request payload cap",
            "What is the request payload cap, in KB, on {project}'s API?",
            "number",
            ("Requests to {project}'s API are capped at {value} KB.",),
            choices=("256", "512", "1024", "2048", "4096", "8192"),
        ),
        FactTemplate(
            "cost_center",
            "cost center",
            "Which cost center is {project}'s cloud spend charged to?",
            "ident",
            ("Charge {project}'s cloud spend to cost center {value}.",),
            low=1_000,
            high=9_999,
            prefix="CC-",
        ),
        FactTemplate(
            "incident",
            "postmortem incident number",
            "Which incident does {project}'s open postmortem cover?",
            "ident",
            ("The open postmortem for {project} covers incident {value}.",),
            low=1_000,
            high=99_999,
            prefix="INC-",
        ),
    ),
    task_titles=(
        "Document the {component} API",
        "Reduce cold starts in the {component}",
        "Add an integration test suite for the {component}",
        "Add retries to the {component}",
        "Fix pagination in the {component}",
        "Migrate the {component} to the new queue",
        "Write a runbook for the {component}",
        "Load-test the {component}",
        "Remove the legacy flag from the {component}",
        "Add metrics to the {component}",
        "Upgrade dependencies in the {component}",
        "Backfill missing rows for the {component}",
        "Rotate credentials used by the {component}",
        "Add alerting for the {component}",
        "Split the {component} config by environment",
    ),
    scoped_policies=(
        ScopedPolicy(
            "freeze",
            "deploy freeze",
            (
                "Deploy freeze on {project}: no deploys to {targets} until {date}.",
                "Until {date}, nothing ships to {targets} — that's the {project} deploy freeze.",
            ),
            dated=True,
        ),
        ScopedPolicy(
            "pairing",
            "mandatory pairing rule",
            (
                "Mandatory pairing rule: any change to {targets} needs a second engineer pairing on it.",
                "{project}'s mandatory pairing rule: for {targets}, nobody merges solo.",
            ),
        ),
        ScopedPolicy(
            "read_only",
            "read-only window",
            ("During the audit, {targets} are in a read-only window until {date}.",),
            dated=True,
        ),
        ScopedPolicy(
            "extra_review",
            "security review requirement",
            (
                "Security review requirement: changes touching {targets} need a security review before release.",
            ),
        ),
        ScopedPolicy(
            "canary_only",
            "canary-only rollout rule",
            ("Canary-only rollout rule until {date}: {targets} only roll out through the canary.",),
            dated=True,
        ),
        ScopedPolicy(
            "verbose_logging",
            "verbose logging requirement",
            (
                "Verbose logging requirement: keep verbose logging on for {targets} while we chase the bug.",
            ),
        ),
    ),
)
