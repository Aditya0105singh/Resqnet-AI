# Rescue crew app

`/crew/:unit` is a phone-first app for the crew of one boat or ground team. The dispatcher's Command page links to it from any unit ("Open crew app").

## Crew-driven units

The **Take crew control** button sends `CREW_MODE {resource_id, on}`. It switches a unit from automatic execution to crew-driven, where each mission step waits for the crew:

```
awaiting_ack ─ACK─▶ acked ─DEPART─▶ en_route ─ARRIVED─▶ on_scene ─BOARDED{count}─▶ boarded
     │                                                                            │
  5 min without ACK: mission cancelled, back to negotiation        DEPART ─▶ en_route_shelter
                                                                                  │
                                       at_shelter ◀─ARRIVED (at the shelter node)─┘
                                            └─COMPLETE─▶ people handed over, mission completed
```

- **Movement.** The unit only moves while `en_route` / `en_route_shelter`. Arrival, boarding and hand-over are never automatic.
- **Arrival is validated.** `ARRIVED` is accepted only when the unit is actually at the incident or shelter node.
- **Boarding.** `BOARDED {count}` caps the load at the crew's count, for example when someone refuses to leave. The people left behind keep the incident open. A count of 0 runs the on-scene "nobody here" path.
- **Escalation.** `UNSAFE_LANDING` closes the next route segment, so everyone replans. `CANNOT_CONTINUE` runs the unit-failure path: passengers are stranded safely as a new urgent incident, and the mission is reassigned.
- **Automatic units are unchanged.** All simulation hashes are identical to before.

## Offline and reconciliation

Every crew action is a `CREW_UPDATE {resource_id, assignment_id, action, event_uuid, client_tick, …}` event sent through the normal events API, so it is replayable.

- **Outbox.** The app appends each action to an outbox kept in `localStorage` and sends it in order when there is signal. The **simulate no signal** switch demonstrates this; the app also respects the browser's offline state.
- **Idempotent.** The engine records every `event_uuid`. A resent update is accepted as a no-op, shown as **duplicate**, and never applied twice.
- **Reconciled against the live mission.** An update is applied only if its mission is still the unit's live mission and the step is valid now. Otherwise it is **rejected with the reason**, for example: "mission A-006 is cancelled: operator cancelled (dispatcher sent a closer unit); your depart update was not applied".
- **Stale view.** The last mission view is cached on the phone, so the crew still sees the target, people and route without signal, with a "last update t=…" stamp.

## Screens

- **Mission:** a step tracker; the incident with the people expected and waiting, and the original SOS text (from WP6) when there is one; the shelter and ETAs; the accept deadline; one large button for the step that is valid now.
- **Route:** a mini-map of the remaining route with blocked segments in red, and a list of segments with closure reasons.
- **Escalate:** "next segment is unsafe" and "cannot continue" with a reason and confirmation.
- **Updates:** queued, applied, duplicate and rejected items, with reasons.

## Not done

- **No service worker.** The app shell is not cached for a cold start without network; offline handling covers an app that is already open.
- **No device GPS.** Position comes from the simulation.
- **No push notifications** for new missions; the app polls every 1.5 s.
