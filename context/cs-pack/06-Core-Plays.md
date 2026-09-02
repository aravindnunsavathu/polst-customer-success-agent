**Polst**** — Core Plays (v0.1)**

**Four plays, not a playbook.** These are hypotheses about what works, written short enough that revising them is cheap. Each has a trigger, steps, an exit test, and a metric. After two quarters, keep what worked, kill what did not, and *then* write the playbook.

**Rule for every play:** log the outcome. A play you cannot evaluate is a ritual.

# **Play 1 — Onboarding to first value**

**Trigger:** contract signed / handoff received from Sales.

**Goal:** a customer-confirmed result, not a launched campaign. Launching is the milestone; the result is the goal.

**Target:** first campaign launched by day [14]; first confirmed result by day [45].

## **Steps**

| **Day** | **Step** | **Output** |
| --- | --- | --- |
| −3 | **Handoff review.** Accept or reject the Sales handoff against the criteria in §Handoff below. | Accepted handoff or a returned one |
| 0 | **Kickoff call.** Map stakeholders. Ask directly: *what has to be true in 90 days for this to have been worth it?* | Success criteria written and sent back for confirmation |
| 0 | **Name the second creator.** Not "who will use it" — *who are the two people.* | Two named creators per department |
| 1 | **Send written success criteria** for the customer to confirm in writing. | Confirmed criteria in the account plan §3 |
| 3–7 | **Enablement session** with both creators. Build the first campaign live in the session rather than teaching abstractly. | First campaign drafted |
| ≤14 | **First campaign launched** | Launch |
| 14 | **Post-launch debrief.** What worked, what was harder than expected. | Friction log → Product |
| 21 | **Second campaign** — by the customer, with CS observing rather than driving | Evidence of self-sufficiency |
| ~45 | **Value confirmation.** Take the result back to the economic buyer *in their metric*, and ask them to confirm it. | Value doc v1 |
| 45 | **Expansion seed.** With a confirmed result in hand, ask: which other department has this same problem? | Named next department |

## **Exit test**

[  ] Result documented and customer-confirmed [  ] ≥2 active creators [  ] second campaign customer-initiated [  ] economic buyer has seen the result

## **Common failure and the counter**

The customer launches one campaign, declares onboarding done, and volume flattens at one campaign a month. **Counter:** never treat launch as the exit. The exit is the *second customer-initiated campaign*, because that is the first evidence the product produced enough value to be repeated.

## **Handoff criteria — CS may refuse an incomplete handoff**

[  ] Stated business objective, in the customer's words [  ] Named economic buyer [  ] Named intended creators [  ] Departments in scope [  ] Commercial terms incl. any commitment [  ] Anything promised during the sale that is not yet true

*(Refusal is not obstruction — it is the only mechanism that keeps handoff quality from degrading. Get it agreed in the Charter)*

# **Play 2 — Decay intervention**

**The most important play under per-campaign pricing.** Decay is churn, arriving quietly.

**Triggers (any one):**

- 90-day volume ratio <0.85

- Zero campaigns in 30 days for a previously active account

- A live department drops to zero creators, or a single-creator department's creator goes inactive [14] days

- Commitment utilization pace implies <70% consumption by term end

- Champion departure detected

**Response time:** T1 within 3 days · T2 within 10 days · T3 automated sequence.

## **Steps**

- **Diagnose before contacting.** Which department, which creator, when did it start? Decay is almost always local — one department or one person — not account-wide. Contacting the buyer with "we noticed usage is down" when the cause is one creator on parental leave wastes credibility.

- **Classify the cause.** The response differs entirely by cause:

| **Cause** | **Signal** | **Response** |
| --- | --- | --- |
| Person left / changed role | Creator deactivated or dormant | Re-seed: identify and enable a successor. Fastest recoverable case. |
| Never got value | Low repeat rate, low quality metric | Back to Play 1. Re-establish the objective; this is an onboarding failure surfacing late. |
| Product friction | Rising abandonment, tickets, long create→launch | Fix or work around; route to Product with evidence |
| Seasonal / cyclical | Same dip last year | **No intervention.** Log it and adjust the baseline. |
| Budget / priority shift | Buyer disengaged, org change | Exec-to-exec. Lead with the documented value. |
| Competitive displacement | Often invisible until late | Exec-to-exec, fast |

- **Contact the right person.** Creator-level cause → creator. Account-level cause → economic buyer.

- **Lead with their outcome, not our usage data.** *"You were tracking toward 5-day distribution — are you still hitting that?"* opens a conversation. *"Your usage is down 18%"* opens a defense.

- **Agree one concrete action with a date.** Not "let's reconnect next quarter."

- **Log the cause.** Non-negotiable. This is the raw material for every improvement to the model and the product.

## **Exit test**

[  ] Cause classified and logged [  ] Concrete action agreed with a date [  ] Volume recovering, OR the account is correctly reclassified with a lower baseline [  ] If unrecoverable: reason documented and routed to Product/Sales

## **Metric**

Recovery rate — % of decay events where volume returns to ≥90% of baseline within 90 days. Also track **lead time**: how long between the trigger firing and the intervention. If lead time exceeds 14 days routinely, the trigger is not being monitored.

# **Play 3 — Renewal / recommitment**

**Trigger:** [20] days before renewal or commitment end.

**Note:** under consumption pricing the renewal moment may be commercially weak — the customer may simply keep consuming. Do not let that make it invisible. It is your best structured opportunity to convert ad-hoc volume into commitment and to reset the baseline upward.

## **Steps**

| **T-minus** | **Step** |
| --- | --- |
| 20 days | **Health and evidence check.** Is the value doc current and customer-confirmed? If not, that is the whole job for the next 30 days. |
| 20 days | **Utili****z****ation check.** If a commitment is under-consumed, this needs solving *before* the commercial conversation, not during it. Under-utilization is the single strongest argument the customer has for reducing commitment. |
| 20 days | **Stakeholder check.** Is the economic buyer the same person? Has the exec sponsor engaged this quarter? Re-establish now, not at T-5. |
| 15 days | **Value review with the economic buyer.** Their metric, their baseline, the delta. Ask them to state the value back to you — what they say is what they will repeat internally. |
| 10 days | **Propose the next period**, framed as a growth plan: departments to launch, volume that implies, tier that unlocks. Anchor on their trajectory, not last year's number. |
| 5 days | **Surface objections deliberately.** Ask what would stop this. Silence at T-5 is not agreement. |
| 5 days | Paper it |
| +7 days | **Post-renewal debrief.** What almost went wrong? Feed it back to Play 2 triggers. |

## **Under-utili****z****ation sub-play**

If a committed account is pacing below ~70%:

- Diagnose — is it decay (Play 2), or was the commitment simply oversold?

- If oversold at the point of sale, say so internally. That is a Sales-handoff finding, not a CS failure.

- Convert the gap into a *reason to expand*: unused capacity is the cheapest possible way to launch a new department.

- Never let the term end quietly with a large unused balance. That number becomes the customer's negotiating position.

## **Exit test**

[  ] Recommitment secured at ≥ prior volume [  ] Value doc confirmed [  ] Growth plan agreed [  ] Debrief logged

# **Play 4 — Expansion qualification**

**Trigger:** an account is Healthy, has a customer-confirmed result, and has ≥1 addressable department not yet live.

**Principle:** never run this before a documented result exists. Expansion sold on relationship rather than evidence produces departments that go dark in two quarters — which under consumption pricing shows up as a volume spike followed by decay, the worst possible pattern.

## **Qualification gate — all must be true**

[  ] Documented, customer-confirmed result in the last 2 quarters

[  ] Health Healthy for ≥60 days

[  ] Existing departments are not single-threaded (fix that first — expanding on a fragile base multiplies fragility)

[  ] Named target department with a named owner

[  ] Champion willing to make an introduction

[  ] Budget path understood — same budget holder or a new one?

*If the last is a new budget holder, this hands to Sales (doc 01 §4). If it is the same, CS runs it.*

## **Steps**

- **Map the addressable footprint** — at kickoff, not now, ideally. Update it.

- **Build the internal case with the champion.** The champion presents it internally; CS supplies the evidence. Expansion sold by an internal advocate lands far better than expansion sold by a vendor.

- **Introduce to the target department.** Position as *the problem they already have*, not as the tool the other department uses.

- **Run a scoped pilot** — a defined number of campaigns with a success criterion, not an open-ended trial.

- **Then run Play 1 for the new department.** A new department is a new onboarding. Treating it as an extension of an existing account is the commonest cause of expansion that fails to stick.

## **Exit test**

[  ] New department live with ≥2 creators [  ] First campaign launched within [21] days [  ] Departmental success criteria documented [  ] Volume sustained past 90 days

## **Metric**

**Expansion durability** — % of new departments still running ≥1 campaign/month at 180 days. This matters more than departments added. A department added and lost is worse than neutral: it consumed CS capacity and taught the account that Polst does not stick.

# **Play backlog — not yet written, in rough priority order**

- **Champion transition** — when a champion leaves. Currently handled inside Play 2, but likely deserves its own play given the single-threading risk.

- **Second-creator seeding** — a proactive play to eliminate single-threaded departments before they fail.

- **Advocacy / reference** — turning Protect-quadrant accounts into references.

- **Win-back** — for accounts that decayed to zero.

- **Escalation** — when something breaks badly.

Do not write these until the first four have been run enough times to know whether their structure holds.

# **Play performance log**

Fill this in as plays run. It is what turns v0.1 into an actual playbook.

| **Play** | **Times run** | **Exit test met** | **Notable failure mode** | **Change proposed** |
| --- | --- | --- | --- | --- |
| 1 — Onboarding |  |  |  |  |
| 2 — Decay |  |  |  |  |
| 3 — Renewal |  |  |  |  |
| 4 — Expansion |  |  |  |  |

	Polst CS · Core Plays	Page 1 of 2