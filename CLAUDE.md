# Polst CS Agent Platform

## What this repo is

An internal agentic operations platform for Polst's Customer Success function. Polst sells a
binary-poll product and **prices per campaign**, which means churn arrives as gradual volume
decay rather than as a cancellation. This system detects that decay early and runs most of the
resulting work.

Owner: VP Customer Success. Reports to CEO. Assume a team of roughly one engineer.

## Read before doing anything

The full technical brief, including architecture, data model, agent specs, autonomy matrix,
and build phases:

@BUILD-PROMPT.md

## Functional specification

The CS Foundations Pack is the functional spec. Where it and BUILD-PROMPT.md conflict, ask.
Read on demand rather than all at once — 00 first for orientation, then whichever applies.

- @context/cs-pack/00-CS-Foundations-Overview.md — start here; consumption-pricing consequences and the revenue driver tree
- @context/cs-pack/01-CS-Charter-and-Mandate.md — what CS owns, decision rights, commercial model answers
- @context/cs-pack/02-Customer-Health-Model.md — **scoring formulas, weights, bands, overrides.** Source of truth for the metrics layer
- @context/cs-pack/03-Instrumentation-Requirements.md — **the data contract.** Tier 1 fields are blocking
- @context/cs-pack/04-Segmentation-and-Coverage-Model.md — tiers, coverage levels, capacity math
- @context/cs-pack/05-Account-Plan-Customer-1.md — account plan schema, with a worked example
- @context/cs-pack/06-Core-Plays.md — **the four plays the agents implement.** Triggers, steps, exit tests, metrics
- @context/polst-company-product.md — product and pricing basics

## Existing trackers — the current manual system

CSV exports of the spreadsheets CS runs on today, formulas preserved as text. These are the
behaviour this platform has to reproduce and then exceed. Read them when implementing scoring;
do not treat them as a schema to copy.

- `context/trackers/health-portfolio-tracker__*.csv` — live scoring, config, volume trend, portfolio view
- `context/trackers/coverage-capacity-model__capacity-model.csv` — coverage and capacity arithmetic

## Standing rules

- **Scoring is deterministic.** No LLM ever produces a score, ratio, or percentage. `/metrics`
  must run with no network, no credentials, and no AWS client.
- **Fail loud on missing data.** Absent inputs yield a null score with a named reason, never a
  default or an imputed value.
- **Gates are enforced in code, not in prompts.** The expansion qualification gate especially.
- **No volume-pushing.** No agent output may have "run more campaigns" as its primary call to
  action. Outreach leads with the customer's stated objective.
- **Nothing customer-facing sends without human approval** in v1.
- **Every play run closes against its exit test with a logged outcome.**
- No agent framework. Orchestration is our own plain Python. See BUILD-PROMPT.md §11.
- Infrastructure is Terraform only. No console-created AWS resources.

## Working agreement

Build in the phases in BUILD-PROMPT.md §12, one at a time, with a working demo at the end of
each. Do not scaffold the whole application in one pass. Surface disagreements with the brief
before implementing, not after.
