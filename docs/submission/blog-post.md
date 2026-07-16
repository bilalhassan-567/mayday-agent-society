# We built an AI society that argues about outages — and it's 3× more reliable than one agent

*How a team of Qwen-powered agents watch a live app, debate what broke, prove their fix
against reality, and get better every time.*

---

## The problem with one smart agent

Give a single large language model your logs, your metrics, and the ability to run
commands, and it will confidently diagnose an outage. Sometimes it's right. The trouble is
the other times: a lone agent that is *confidently wrong* will apply a fix that doesn't
work, or one that makes things worse, and then tell you it's done. There's no second
opinion, no adversary, and — most dangerously — often no check that the system actually
came back.

Incident response is exactly the domain where that failure mode is both most tempting to
automate and most costly to get wrong. So we asked a narrower, more honest question: **can
a *society* of agents — with disagreement, staked confidence, and a referee grounded in
reality — be measurably more trustworthy than one agent working alone?** And can we *prove*
it rather than assert it?

That's Mayday, our entry for the Global AI Hackathon with Qwen Cloud, Track 3: Agent
Society.

## The setup: a patient that really breaks

We built a real Laravel CRM — login, dashboard, users, orders, reports — and called it the
**patient**. Then we built eight fault injectors that break it in controlled but genuine
ways: five corrupt a real configuration value (a database pointer, an exhausted connection
pool, a bad API key, a renamed route), and three corrupt real source code (a misspelled
method, a broken template). Each fault leaves a real clue trail in the logs, exactly as a
production incident would.

The single most important design decision is what we call the **golden rule**: there is a
private ledger that records what the injector broke — but *nothing that counts as the
system working is ever allowed to read it*. Not the app's routes, not its health check, not
any agent, not any tool. The ledger exists only to *grade* a run after the fact. Every fix
the agents make repairs the app's real state, discovered from evidence — never copied from
an answer key. Without that rule, a multi-agent demo is theatre. With it, everything you
see is real.

## The society: watch, bid, argue, verify, learn

When the patient breaks, here's what happens — end to end, autonomously:

**A Watchman** patrols every page of the app and opens an incident the moment one fails.

**A Dispatcher** classifies the failure and runs a **trust-weighted auction**. Two
investigator agents bid for the case, and each bid is weighted by how accurate that agent
has been on *this category* of failure in the past. Skin in the game, from the first step.

**Two Investigators** go to work — and here's the twist that makes the society real: they
have *different tools*. One can read source code and tail exceptions; the other leans on
metrics and configuration inspection. Because they see different slices of the truth, they
often reach different conclusions. So they **debate**: each stakes a confidence bet on its
hypothesis, cites live tool evidence (the actual exception, the real config value — not a
runbook), attacks the other's reasoning, and then holds or revises.

**A deterministic Adjudicator** settles it — but *not* by picking the better argument.
It **trials each proposed fix against the real health check**: apply the candidate, ask the
app if it recovered, then revert. The winner is whatever genuinely heals the patient. This
is the honesty guarantee made mechanical: "resolved" can only ever mean the app actually
came back.

**A Verifier** commits the cure. Config fixes apply autonomously; source-code changes pause
for a single human approval click (you don't let an AI rewrite your code unwatched); and
anything that doesn't hold is rolled back.

Finally, **trust settles** toward whoever was right, and a **case file** is written to
memory. The next incident of that kind starts with hindsight — the society gets measurably
better over time.

All of this streams into a **War Room**: a siren when an incident opens, operator stations
showing each agent's reasoning in speech bubbles, trust bars that shift as the society
learns, a live mean-time-to-resolve clock, the human-approval modal, and the patient page
itself going from a 500 error back to healthy in an embedded frame.

## The proof: a fair fight against one agent

Track 3 asks for efficiency gains over a single-agent baseline, so we built one — the same
model, the same tools, the same apply-and-verify path — and benchmarked both over all eight
faults on **`qwen-max`**. The critical fairness detail: we gave the lone agent the *same
improved prompts*, so the only thing that differs between the two is the society mechanism.

| Mode | Resolved | Rate | Mean MTTR |
| --- | --- | --- | --- |
| **Society** | **6 / 8** | **75%** | 91.2s |
| Single-agent baseline | 2 / 8 | 25% | 40.0s |

**Three times the resolution rate.** And the *where* is the whole story: the society wins
exactly on the hard faults — all three code bugs and the routing failure — where the lone
agent bails out early or commits a fix that doesn't work. The society is slower by about
fifty seconds per incident, because debating and trialing fixes takes time. That's not a
bug; it's the same tradeoff a real on-call organization makes every day: a little latency
for a lot more reliability.

## What was actually hard

It wasn't the agents. It was the honesty. Guaranteeing that no diagnosis path could ever
reach the fault ledger, and that "resolved" always meant a real health check passed, shaped
the entire architecture. The second-hardest part was resisting the urge to make the society
look good with better prompting — the fair benchmark meant improving the baseline in
lockstep. And a small but instructive one: the dev server is single-threaded, so a health
check during an active fault can take ten seconds; the War Room caches health in a
background thread so the live UI never freezes.

## What we learned

Disagreement is a feature. A second agent with different tools and a stake in being right
catches the confident-but-wrong fixes a lone agent ships. And a referee grounded in reality
— *did the app actually recover?* — is worth more than any amount of clever argument. That
combination, not the number of agents, is what made the system trustworthy.

## What's next

We're deploying the patient and the society to Alibaba Cloud (ECS + ApsaraDB RDS Postgres +
OSS), which also closes out the one fault whose healthy value only exists in a real
production environment. Then: a bigger fault catalog, and pushing the learning curve
further with richer case-file memory.

## Built on Qwen

The whole society runs on Qwen — `qwen-max` on Qwen Cloud for the real numbers, and
`qwen2.5` via Ollama for fast local iteration, switchable with a single environment
variable. The tool layer speaks the Model Context Protocol; trust and memory persist in
SQLite, ready for Postgres in production; and the War Room is dependency-free standard
library, so there's nothing to install to watch a society of AI agents argue an outage back
to health.

*Everything in our demo is real: the break, the debate, the fix, the recovery. That was
the point.*
