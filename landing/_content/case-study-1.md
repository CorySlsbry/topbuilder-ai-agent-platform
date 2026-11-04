# The Jobs That Quietly Lost Money: Finding Live Margin Before Month-End

_Representative 14-technician residential HVAC contractor (~$7M annual revenue), running ServiceTitan in the field and QuickBooks Online in the back office_

> DISCLAIMER: Illustrative benchmark scenario, not a real named customer. Top Builder AI is pre-launch, so no live client results exist yet. Every figure below is modeled from published 2026 HVAC industry benchmarks (ACCA Financial Benchmarking Study; 2026 margin and pricing studies from Steph's Books, FieldCamp, ServiceTitan, BuildOps, and others) applied to a representative 14-tech, ~$7M shop. The numbers describe what the math supports for a contractor at this profile, not a measured outcome from a specific company.

## Challenge
This shop looked healthy on paper. The trucks were booked, revenue was up, and the company P&L closed somewhere around 6 percent net most months, right at the residential HVAC median. The problem was that nobody knew which jobs made that money and which ones lost it until the books closed weeks later. Margin was a month-end surprise, not a daily number.

Three leaks ran underneath the surface. First, job costing happened after the fact. ServiceTitan held the field data and QuickBooks held the financial truth, but the two were reconciled by hand long after the crew left the site, so a job that ran over on labor or pulled extra parts only showed up as a thinner number on a report nobody read in time to act. Second, the flat-rate pricebook was stale. Material costs had climbed 12 to 18 percent since 2023 and parts were rising 5 to 10 percent a year, but the book had not kept pace, so a slice of the work was being sold below its real cost without anyone deciding to do that. Third, truck stock leaked. A tech grabbed a capacitor for one job and nobody recorded it, so the cost floated into general shrinkage instead of landing against the job that consumed it. The installs that looked like 40 percent gross on the estimate were quietly closing lower once callbacks, real on-site hours, and unbilled parts were counted.

None of this was incompetence. It is the default state of a busy shop whose tools were built to dispatch and invoice, not to tell you the margin on the job while the truck is still in the driveway.

## Approach
Top Builder AI installed on top of the systems the shop already ran. It did not replace ServiceTitan or QuickBooks. It sat between them as an integration bridge: field data flows out of ServiceTitan, Top Builder AI categorizes it, costs it, and reconciles it, and the result lands as financial truth in QuickBooks. Three agents did the work.

The Financial agent computed margin per job continuously instead of at month-end. Every dollar and hour came from pure, tested code, not from a language model, so the figures were exact and auditable. The agent could narrate and advise on a job, but it was structurally blocked from changing a number, which means it cannot inflate or hallucinate a margin. Jobs that crossed below their target margin surfaced the same day, while the shop could still act on them, instead of as a line on a report after the crew had moved on.

The Pricebook agent re-costed the flat-rate book against current material and labor cost. It flagged every line that had drifted below its target margin from inflation and proposed a corrected price, with the reasoning shown. Nothing changed automatically. The owner reviewed each proposal, approved or rejected it, and kept a full undo and audit trail. Structured re-pricing is the single most documented margin lever in the trade, and this put it on a continuous footing instead of a once-a-year scramble.

The Inventory agent tied truck stock to job numbers. Parts pulled from a truck were attributed to the job that consumed them, so material cost reduced that job's margin instead of disappearing into general shrinkage. That closed the gap between the estimate's gross and the real gross.

Every agent ran advisory by default, set to Off, Approve-first, or Auto per the owner's comfort. Data stayed isolated to this shop under row-level security with encrypted credentials, so its numbers never trained another contractor's agents. Founder Cory Salisbury ran the install hands-on.

## Results (modeled)
- **Net profit margin lift modeled in year one: +3 to +4 points (about 6% to ~9-10%)** — ACCA benchmarking puts the residential HVAC median near 5.8% net and the top quartile near 13.2%. Modeled as moving partway from median toward the achievable band, not to top-quartile, to stay conservative. On ~$7M revenue, each net point is ~$70K.
- **Modeled annual profit recovered: ~$210,000 to ~$280,000** — A 3 to 4 point net margin gain applied to ~$7M revenue (each point ~$70K). Recovery, not new sales: pricing the work to its true cost and attributing material cost to the job that consumed it.
- **Margin lift attributable to re-costing the flat-rate book: 15-30% improvement range, modeled at the conservative end** — Multiple 2026 pricing studies report contractors who implement structured pricing guides see 15-30% profit-margin improvement in the first year. Modeled at the low end given a shop already at median, not bottom-tier.
- **Stale-pricebook drift the agent corrects for: 12-18% material inflation since 2023; 5-10% parts increase per year** — Published 2026 HVAC cost data on copper, aluminum, steel, and components. This is the gap a once-a-year (or never) repricing cadence leaves uncovered between updates.
- **Unbilled truck-stock leakage recaptured against jobs: Targets <10% inventory shrinkage; recovers parts cost into per-job margin** — ACCA HVAC guidance cites shops targeting 10% or less shrinkage. Attributing parts to job numbers moves that cost out of general shrinkage and onto the consuming job, correcting an install's real vs. on-paper gross.
- **Time from job completion to known margin: Same day vs. weeks at month-end** — Deterministic per-job costing runs continuously off the ServiceTitan-to-QuickBooks bridge instead of a manual month-end reconciliation. Modeled, reflecting the design rather than a measured client cycle time.

## Representative quote
The kind of thing an owner tells us: we were busy all year and still wondered where the money went. Turns out a handful of jobs lost money every month and we never knew until the books closed, by then it was too late to do anything about it. Now I see the margin on a job the day we finish it, and the price book actually reflects what parts cost today.

_Timeframe: Modeled over a representative first-year engagement (year-one margin figures), with per-job margin visibility from the first reconciliation cycle_
