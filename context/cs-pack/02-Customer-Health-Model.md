**Polst**** Customer Health Model**

**Purpose:** define what a healthy Polst customer looks like in observable, measurable terms — so that "this account feels fine" is replaced by evidence, and so that decay is caught while it is still reversible.

**Version:** 0.1.

**Owner:** VP Customer Success

# **1. Design principles**

- **Observable, not interpretive.** Example: Quantify "Effective ongoing usage" as "≥2 active creators in ≥2 departments running ≥8 campaigns per quarter with a ≥80% completion rate".

- **Relative to the account's own baseline, not to an absolute.** An account running 100 campaigns/quarter that drops to 60 is in crisis. An account running 6 that rises to 10 is thriving. Absolute thresholds punish small accounts and hide decay at large ones. Score on trajectory *and* level.

- **Leading over lagging.** By the time NRR moves, the cause is 2–3 quarters old.

- **Volume is always paired with quality.** 

- **Fewer signals, measured**** well****, beat many signals estimated.** Start with what you can actually instrument. A score built on fields nobody fills in is worse than no score.

# **2. The healthy customer, by stage**

Currently as hypotheses. To be updated when we have data from a few customers.

## **Day 0–30 — Onboarded**

| **Dimension** | **Healthy** | **At risk** | **Critical** |
| --- | --- | --- | --- |
| Kickoff completed with named stakeholders | Yes, ≥3 contacts mapped incl. economic buyer | Kickoff done, 1–2 contacts | No kickoff |
| Success criteria documented and customer-confirmed | Written, agreed, in the account plan | Discussed, not written | Absent |
| First campaign launched | By day [14] | By day [30] | Not launched |
| Trained creators | ≥[2] per initial department | 1 | 0 |
| Exec sponsor identified (customer side) | Named and has met CS | Named only | None |
| First campaign status | Success criteria achieved or on track | Success criteria may not be achieved | Success criteria not achieved |

**Stage exit test:** first campaign launched, success criteria documented and either achieved or on track.

## **Day 31–90 — Achieving first value**

| **Dimension** | **Healthy** | **At risk** | **Critical** |
| --- | --- | --- | --- |
| Campaigns run in first 90 days | ≥[6] | [2–5] | ≤1 |
| Customer-confirmed result from ≥1 campaign | Yes, documented | Claimed, not documented | None |
| Active creators | ≥[2] | 1 | 0 |
| Departments live | ≥[1] fully, [2nd] identified | 1, no pipeline | 0 |
| Time from campaign N to campaign N+1 | Shortening | Flat | Lengthening |
| Support tickets on core workflow | Declining | Flat | Rising |

**Stage exit test:** a documented, customer-confirmed result *and* ≥2 active creators.

The second creator matters more than it looks. A department with one creator has a single point of failure whose departure zeroes the department's revenue. Under consumption pricing this is the most common silent decay mechanism.

## **Day 91–180 — Self-sustaining**

| **Dimension** | **Healthy** | **At risk** | **Critical** |
| --- | --- | --- | --- |
| 90-day campaign volume vs. prior 90 days | ≥100% | 70–99% | <70% |
| Campaigns initiated without CS prompting | ≥[80]% | [40–79]% | <40% |
| Departments live | ≥[2] | 1 | 1, declining |
| Creators per live department | ≥2 | 1 | 1 |
| Value doc refreshed | Within 90 days | 90–180 days | >180 days or never |
| Exec sponsor engaged (met in last quarter) | Yes | Contactable | Gone / unresponsive |
| Campaign quality metric | At or above cohort median | Below median, stable | Below median, declining |

**Stage exit test:** volume sustained without CS prompting, across ≥2 creators.

## **Steady state — Growth account**

The bar rises: volume trending up, ≥3 departments, ≥2 creators each, a refreshed value doc, an engaged exec sponsor, and a reference-willing champion.

# **3. Health score — dimensions and weights**

Six dimensions. Each scored 0–100; weighted composite. Weights are a starting hypothesis.

| **#** | **Dimension** | **Weight** | **What it measures** | **Why it earns its weight under per-campaign pricing** |
| --- | --- | --- | --- | --- |
| 1 | **Volume trajectory** | 30% | 90-day campaign volume ÷ prior 90-day volume, floored/capped | This *is* the revenue line. Direction matters more than level. |
| 2 | **Breadth** | 20% | Departments live × creators per department, vs. account potential | The concentration risk. Volume from one person is fragile volume. |
| 3 | **Value reali****z****ation** | 20% | Documented, customer-confirmed result, and its recency | The only defense against champion turnover and budget review |
| 4 | **Campaign quality / outcome** | 15% | See §4 | Leading indicator of whether volume repeats |
| 5 | **Relationship coverage** | 10% | Contacts mapped, exec sponsor engaged, champion identified | Catches the churn causes usage data never predicts |
| 6 | **Sentiment ****&**** friction** | 5% | Support ticket trend, escalations, survey response | Noisy at low volume; keep the weight small |

**Score bands:**

| **Band** | **Score** | **Meaning** | **Action** |
| --- | --- | --- | --- |
| Healthy | 75–100 | On track; expansion candidate | Play 4 (expansion qualification) |
| Watch | 50–74 | One or more dimensions soft | Named intervention within 14 days |
| At risk | 30–49 | Decay underway | Play 2 (decay intervention), exec visibility |
| Critical | 0–29 | Recovery unlikely without exec action | Exec-to-exec, or plan the loss and capture the reason |

## **Overrides (score-independent)**

Some conditions cap the score regardless of the composite. Without these, a high-volume account can mask a fatal problem.

| **Condition** | **Cap** |
| --- | --- |
| Champion departed, no successor identified | At risk max |
| Zero campaigns in 45 days | At risk max |
| Zero campaigns in 90 days | Critical |
| No exec sponsor identified after day 90 | Watch max |
| Committed volume utilization <40% with <90 days of term left | At risk max |
| Single creator across the whole account, past day 90 | Watch max |
| Open escalation unresolved >30 days | At risk max |

# **4. Campaign quality — the guardrail metric**

Volume without quality is borrowed revenue. Every volume review includes at least one of these. **You need to pick which one(s) ****Polst**** can actually measure** — this depends on what a campaign does, which is a question for Product.

Candidate quality signals, best first:

| **Signal** | **Strength** | **Can it be ****Instrument****ed****?** |
| --- | --- | --- |
| Customer-stated business outcome achieved (from value doc) | Strongest — but manual | Manual |
| Campaign completion rate (launched vs. abandoned/draft) | Strong, cheap | Yes |
| In-product engagement/response rate of the campaign's audience | Strong if applicable | Yes |
| Repeat rate — % of creators who run another campaign within 60 days | Strong proxy; catches "ran it once, never again" | Yes |
| Time from campaign creation to launch | Weak alone, useful as a friction signal | Yes |
| Campaigns using >1 feature / template beyond default | Weak; indicates depth | Yes |

**Anti-pattern to watch for:** a rising campaign count with a falling repeat rate means creators are trying and not returning. This looks like growth for one quarter and then reverses. If you can only instrument two things, make them *volume* and *repeat rate.*

# **5. Scoring the dimensions**

Detailed definitions so the score is reproducible across people. Implemented in the accompanying tracker.

**1. Volume trajectory (30%)**

ratio = campaigns_last_90d / campaigns_prior_90d

Score: ≥1.25 → 100 · 1.00–1.24 → 85 · 0.85–0.99 → 65 · 0.70–0.84 → 40 · 0.50–0.69 → 20 · <0.50 → 0

New accounts (<180 days): score against onboarding plan target instead of prior period.

**2. Breadth (20%)**

score = 50 × min(departments_live / departments_target, 1) + 50 × min(pct_departments_with_2plus_creators, 1)

departments_target is your judgement of the account's realistic footprint — record it in the account plan and revisit annually.

**3. Value ****realisation**** (20%)**

100 = documented, customer-confirmed result within 90 days · 70 = within 180 days · 40 = documented but >180 days or not customer-confirmed · 0 = none.

**4. Campaign quality (15%)** — percentile against the cohort on the chosen §4 metric, or a simple 0/50/100 rubric until you have enough accounts to form a cohort.

**5. Relationship coverage (20 pts each, capped 100)**

+20 economic buyer identified · +20 exec sponsor identified · +20 exec sponsor engaged in last quarter · +20 ≥3 contacts mapped · +20 a champion who would take a reference call.

**6. Sentiment ****&**** friction (5%)**

100 = no escalations, tickets flat or falling · 50 = elevated tickets or one resolved escalation · 0 = open escalation or sharply rising tickets.

# **6. Operating cadence**

| **Cadence** | **Activity** | **Output** |
| --- | --- | --- |
| Weekly | Review At-risk / Critical accounts and any account crossing a decay threshold | Named owner + action per account |
| Bi-weekly | Review Watch accounts | Intervention or downgrade to monitoring |
| Monthly | Full portfolio review; NRR roll-up | Portfolio snapshot to CEO/CRO |
| Quarterly | Re-score weights and thresholds against actual outcomes; refresh value docs | Model v(n+1) |

# **7. Calibrating the model — do this, or the score is decoration**

The weights above are guesses. They become real through one exercise, run at the end of each quarter:

- Take every account that churned, decayed >30%, or expanded >30% this quarter.

- Look back at what the model scored them **two quarters before** the outcome.

- Ask: did the score move first, or did the outcome surprise you?

- For every surprise, name the signal that *would* have caught it. Add it, or reweight.

**Track these three model-quality numbers:**

- **Hit rate** — % of decay/churn events that the model flagged At-risk / Critical at least one quarter ahead

- **False alarm rate** — % of At-risk / Critical accounts that recovered with no intervention

- **Lead time** — median days between first amber flag and the revenue impact

A model with a 30% hit rate is worse than useless, because it creates false confidence. If after two quarters it is not beating your own intuition, simplify it — two well-instrumented signals honestly tracked beat six estimated ones.

# **8. Known limitations of v0.1**

- Weights are unvalidated.

- Dimensions 3 and 5 are manually maintained and will decay if not enforced in the account-plan cadence.

- The cohort comparison in dimension 4 needs ~15+ accounts to be meaningful; below that, use the rubric.

- Seasonality is not handled. If Polst customers have seasonal campaign patterns (budget cycles, academic year, retail calendar), a year-over-year comparison must replace the 90-day sequential one for dimension 1. **Check this early** — it is the most likely source of systematic false alarms.

	Polst CS · Customer Health Model	Page 1 of 2