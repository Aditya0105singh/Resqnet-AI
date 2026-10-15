# Demo scripts

**Setup.** Start the backend and frontend (see README), then open **`/demo`**.

Every step on that page runs the real engine and shows what it returned. If a live step ever behaves differently, the screen shows the actual result rather than a scripted one. That is the point.

> The one sentence to leave with the judges: **"RESQNET doesn't just find a rescue route. It keeps rescue decisions coordinated, safe and explainable when the situation changes."**

## Three-minute version (`/demo`, "Run the whole demo" or step by step)

| Time | Step on `/demo` | What to say |
|---|---|---|
| 0:00–0:20 | 1. A flood is unfolding | "Aluva, Kerala: real OpenStreetMap roads and bridges, real terrain around the Periyar. The flood and the incidents are simulated. Every boat, team and shelter is an independent agent negotiating rescues live, under a safety shield." |
| 0:20–0:45 | 2. Citizen SOS in Hindi | "A citizen writes in Hindi. We extract evidence: 5 people, an elderly person, rising water, trapped upstairs, so urgency is 5 by a fixed rule. 'Near the river' is not a location, so we don't invent one: it goes to a human." |
| 0:45–1:00 | 3. Dispatcher places and approves | "The dispatcher calls back: they are at Aluva Market, by the river. Approval re-runs every safety check against the state right now." |
| 1:00–1:20 | 4. Agents negotiate | "Units bid on their own, possibly stale, view of the roads. The cheapest feasible bid wins, a shelter reserves seats, and the shield validates the commit." Click **Open the decision record**. |
| 1:20–1:50 | 5. Break it three ways at once | "Now three things fail at the same minute: the shelter this rescue is heading to fills up, a bridge collapses, and the unit on its way breaks down. The reservation is revoked and the rescue goes to another unit within a few minutes, with zero safety violations." |
| 1:50–2:10 | 6. Crew's updated mission | "The crew sees the new plan on a phone. Every tap is a validated, idempotent event, and updates queued without signal are reconciled when it returns." |
| 2:10–2:35 | 7. Ask the Commander | "Ask why. The answer comes only from the run's records, every claim is cited and checked, and the assistant can only *propose* actions." |
| 2:35–3:00 | 8. Every claim is measured | "Ten paired seeds on the synthetic test city, 95% confidence intervals. On a healthy network the central optimiser is as good or better, and we say so. When the coordinator fails, the agents keep serving: about 10 points more service and 19 minutes faster." |

## Six-minute version

Do the three-minute version, then add:

1. **Offline crew (45 s), `/crew/G1` on a phone-sized window.**
   1. Take crew control and accept a mission.
   2. Tick **simulate no signal** and tap **Depart**; it shows as *queued*.
   3. On `/command`, cancel that mission (Inspect the unit, then *Request reassignment*).
   4. Untick no signal. The queued Depart comes back **rejected** with the dispatcher's reason, and it is never applied.
2. **Message-passing agents and partitions (45 s), `/command`.**
   1. New run → *Network Partition* scenario, strategy *Message-passing*.
   2. Show `LOST` messages and timeouts on `/agents`.
   3. Say: "No strategy commits across the split. Availability drops, never safety."
3. **Disputed reports (30 s), `/command`, *Forwarded SOS Cascade* scenario.**
   1. Open a DISPUTED incident: forwards are counted once, and credible conflicting reports wait for a human (Confirm / Verify / Dismiss).
   2. Mention the measured effect: significantly fewer trips to rumoured victims for every strategy.
4. **Evidence (30 s), `/research`.** Show the PS 27 compliance matrix with test names, the assumptions page, and the data provenance page, including what is *not* real yet.

## Honest answers to likely questions

- **"Is decentralised better?"** On a healthy network, no: centralised is as good or slightly better. Under a coordinator outage, yes, under the stated assumption that peer communication survives. See `/arena` → Published results.
- **"Is this real Kerala data?"** The map is: the app opens on **Aluva, Kerala**, with real OpenStreetMap roads and bridges and Copernicus terrain (Riverbend, the synthetic test city, is still in New run). The *Kerala 2018 flood replay* uses the real river-discharge curve and rainfall timing. The inundation depths, incidents and shelter capacities are simulated or assumed, and our own Sentinel-1 check shows the flood model is useful on Chengannur but weak on Aluva. See `/research` → Data provenance and `docs/flood_validation.md`.
- **"Does the LLM decide anything?"** No. It extracts evidence and answers questions with citations. Urgency, location, safety and approval are deterministic or human.
