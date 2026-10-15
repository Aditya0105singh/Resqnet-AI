# 5-minute judge demo

**Setup:** start the backend and frontend, open `/command`, click **New run** and choose *A · Normal flood*, strategy *Multi-agent*. Speed 2×.

**Opening line:** "Most emergency dashboards tell you where the crisis is. resqnet shows how autonomous rescue resources negotiate, recover and coordinate after the original rescue plan becomes impossible."

### 1. The world (30 s), `/command`
- Riverbend is synthetic: a river, three bridges, five neighbourhoods. Blue haze is flood depth; dashed blue roads are impassable for ground teams, and the wider pale-blue streets can now be navigated by boat.
- There are 12 SOS incidents. Diamond size shows people, colour shows urgency, and dashed outlines are unverified reports.
- Press **Start** and watch the activity feed fill with commitments.

### 2. Real negotiation (45 s), `/agents`
- Open the latest eventful round. Show the message graph: BIDs (dashed), PROVISIONAL_ACCEPT, an agent REJECT with its reason (e.g. "B2 prefers I-007 (cost 0.41 < 0.47)"), shelter RESERVE/ACCEPT, then COMMIT.
- Point out that every message is computed: no LLM, no script. Deferred acceptance makes the matching conflict-free.

### 3. Break it three ways (60 s), `/command`
- Ask a judge to click **Triple failure**. The engine picks a bridge, a committed boat and the shelter with the most inbound reservations from live state.
- In the feed: the bridge closes, the boat is disabled and its commitment cancelled, the shelter revokes its reservations LIFO, and each affected unit renegotiates another shelter. A new round reassigns the stranded request.
- Optionally have the judge also click **Close BR…** or **Fail B…** while the system is still adapting.

### 4. Why did it do that? (45 s)
- Click **why?** on a reassignment. The Decision Inspector shows the evidence and confidence, every candidate's cost broken down into T/R/U/F, the rejections, the shelter negotiation, all safety checks, and "what would change this decision".

### 5. What if? (45 s), `/decision-lab`
- Fork at t≈20 with **+2 boats** (or reopen the bridge) and run both futures.
- Show the synchronised maps and the measured deltas. Point out where the alternative did **worse** (for example fairness or utilisation): results are measured, not promised.

### 6. Fair comparison (30 s), `/arena`
- Run 6 seeds on *triple_failure*. Be candid: the centralised optimiser is about 1–3 minutes faster on mean time-to-service. Multi-agent comes close with stale, partial information and no central coordinator, uses fewer coordination messages, and has zero safety violations across the board.

### 7. Trust (30 s), `/replay` and `/safety`
- **Verify deterministic replay**: "rebuilt N ticks, every state hash matches."
- **Find weakest scenario**: the adversarial search ranks the worst failure combinations it found. Open one in the simulator. "We go looking for where we fail."

**Close:** "They broke the plan three ways. It recovered, explained every change, and let you test whether another decision would have been better."
