---
summary: "The empirical finding that solar PV cost per watt declines roughly 23% with every doubling of cumulative installed capacity — driven by manufacturing scale and process learning, not new physics."
tags: [solar, energy, learning-curves, economics, wrights-law, swanson]
last_updated: 2026-04-27
---

# Swanson's Law

**Swanson's Law** is the empirical observation, named for SunPower founder Richard Swanson, that the cost per watt of solar photovoltaic modules declines by approximately **23 percent for every doubling of cumulative installed capacity**. It is the solar-specific instance of a broader experience-curve pattern (cf. [[wrights-law]]) and has held with remarkable consistency for more than four decades.

The law matters not because the per-doubling number is unusually steep — Wright's Law in aerospace ran around 10 to 15 percent, Moore's Law was a different beast altogether — but because the underlying mechanism is **manufacturing scale and process learning**, not breakthrough physics. This makes the curve unusually robust to interruption: it does not depend on any single research programme delivering, only on production continuing.

## Definition

Formally: let $C(Q)$ be the cost per watt of PV modules at cumulative production $Q$. Swanson's Law states

$$C(2Q) \approx 0.77 \cdot C(Q)$$

with the **23 percent decline per doubling** holding across roughly four decades of data. The coefficient has fluctuated between about 18 and 28 percent depending on the period and the specific module technology measured, but the central tendency is stable enough that energy analysts treat it as a planning input rather than a forecast.

The law applies to *module* cost, not to the full installed system cost (which includes inverters, balance-of-system, labour, and soft costs). Soft costs have not fallen as fast and now dominate the installed price in mature markets — an important caveat to any "solar is free" argument.

## The Numbers

The trajectory is one of the steepest cost declines in the history of any manufactured good:

| Year | Cost per watt (module, USD) |
|------|------------------------------|
| 1976 | ~$106 |
| 1990 | ~$10 |
| 2010 | ~$2 |
| 2020 | ~$0.20 |
| 2024–2026 | ~$0.10 or below |

That is a roughly **thirteen-hundred-fold decline in less than fifty years**. Over the same period cumulative installed capacity rose from under 1 megawatt globally to over 1.5 terawatts — six orders of magnitude. Plotting cost against cumulative capacity on log-log axes yields a remarkably straight line.

## Mechanism

The 23-percent-per-doubling rate is decomposable into several reinforcing learning effects:

- **Wafer thinning.** Silicon wafers have been progressively thinned, reducing material cost per watt.
- **Yield improvement.** Defect rates in cell production have fallen as processes mature.
- **Equipment depreciation.** As PV-specific manufacturing equipment matures, capital cost per watt of capacity drops.
- **Supply chain integration.** Vertical integration (especially in China post-2010) compressed margins and squeezed inefficiencies out of the polysilicon-to-module pipeline.
- **Module efficiency gains.** Each cell converts a slightly larger fraction of incident sunlight than the last, improving watts-per-area.
- **Plant scale.** Doubling plant size reduces per-unit overhead more than proportionally.

None of these is a single breakthrough. Each is a slow accumulation of incremental optimisations. This is why Swanson's Law has been more reliable than (say) battery-technology cost curves that depend on chemistry advances: the solar cost curve is grinding down a well-explored manufacturing landscape, not waiting for a new physical principle.

## Robustness of the Curve

Swanson's Law has survived several events that should have broken it:

- **The 2008–2012 polysilicon spike**, when raw silicon prices briefly rose tenfold, slowed but did not reverse the curve.
- **Trade wars** (US-China tariffs from 2012 onward) shifted the geographic distribution of production but did not change the slope.
- **The Solyndra-era bankruptcies** of 2011–2013 cleared marginal producers without raising prices for buyers.
- **Pandemic supply-chain disruptions** of 2020–2022 caused brief spikes that the curve absorbed within eighteen months.

The robustness is itself the point. Curves that depend on single firms or single technologies break when those break. Swanson's Law depends on the entire global manufacturing complex continuing to scale, and as long as global demand keeps the complex producing, the curve grinds on.

## Why It Matters Civilisationally

The standard reading of Swanson's Law is "solar is getting cheap." The civilisational reading is more consequential: solar is becoming a **flow energy with increasing returns to scale**, in structural opposition to fossil fuels' character as a stock with diminishing returns to extraction (see [[solar-as-flow-vs-fossil-as-stock]] and [[eroi-thresholds]]).

Three implications follow:

1. **The cost of energy diverges from the cost of fuel.** With solar, the cost of the *capture mechanism* falls predictably; the fuel itself (sunlight) is free. The lifetime levelised cost of a kilowatt-hour from new solar is now below the marginal operating cost of many existing fossil plants.
2. **The infrastructure-inheritance pattern (see [[infrastructure-inheritance]]) acquires a new energy substrate.** The Modernity Machine's apparatus, built on coal and oil, can be re-powered on increasing-returns-to-scale solar without rebuilding from scratch.
3. **The wager underneath the [[liveness-machine]] becomes less speculative.** AI's energy appetite, currently a source of nervous arithmetic, becomes a tractable problem if Swanson's Law continues another decade. If the curve breaks, the lightening of intent may end as a brief anomaly.

## Connections

- [[wrights-law]]: Swanson's Law is the solar-PV instance of Wright's broader pattern of cost-declines-with-cumulative-production.
- [[eroi-thresholds]]: Solar's rising EROI — now estimated at 25–30:1 at the useful stage — is partly a downstream consequence of Swanson's Law cost declines compounding over decades.
- [[solar-as-flow-vs-fossil-as-stock]]: Swanson's Law gives the flow-energy regime its increasing-returns character that distinguishes it structurally from the diminishing-returns extraction of fossil stocks.
- [[ephemeralization]]: Buckminster Fuller's "doing more with less" pattern, of which Swanson's Law is one of the cleanest empirical instances on record.
- [[energy-rate-density]]: A continuing Swanson's Law allows civilisational energy throughput to keep rising without exhausting the substrate that supplies it.
