import { Bomb, Construction, Radio, Ship, Split, Tent, TriangleAlert, Waves, Zap } from "lucide-react";
import { useSim } from "../store/sim";
import { Dropdown, MenuItem } from "./ui";

/** Live fault injections with plain-language descriptions. Each posts a real event to the engine;
 * the triple failure's targets are chosen by the backend from live state. */
export function ChaosItems({ onDone = () => {}, extra = false }: { onDone?: () => void; extra?: boolean }) {
  const frame = useSim((s) => s.frame);
  const world = useSim((s) => s.world);
  const inject = useSim((s) => s.inject);
  if (!frame) return null;
  const bridges = (world?.edges ?? []).filter((e) => e.kind === "bridge");
  const used = new Set(frame.resources.flatMap((r) => (r.route ?? []).slice(1).map((n, i) => [r.route[i], n].sort().join("|"))));
  const bridge = bridges.find((b) => frame.edges[b.id] && !frame.edges[b.id][2] && used.has([b.u, b.v].sort().join("|"))) ?? bridges.find((b) => frame.edges[b.id] && !frame.edges[b.id][2]);
  const boat = frame.resources.find((r) => r.kind === "boat" && r.status !== "DISABLED" && r.assignment_id) ?? frame.resources.find((r) => r.kind === "boat" && r.status !== "DISABLED");
  const shelter = [...frame.shelters].sort((a, b) => b.reserved - a.reserved)[0];
  const blackout = frame.resources.find((r) => r.status !== "DISABLED" && r.assignment_id && !r.blackout_until);
  const partitioned = (frame.network?.partitions.length ?? 0) > 0;
  const boats = frame.resources.filter((r) => r.kind === "boat" && r.status !== "DISABLED" && !r.blackout_until);
  const cut = [...boats.filter((r) => r.assignment_id), ...boats.filter((r) => !r.assignment_id)].slice(0, 3).map((r) => r.id);
  const bname = bridge ? bridge.name || bridge.id : "";
  const go = (fn: () => void) => () => {
    fn();
    onDone();
  };
  const open = frame.incidents.find((x) => x.status !== "RESCUED" && x.status !== "FALSE_ALARM");
  return (
          <>
            <MenuItem tone="crit" icon={<Bomb className="size-4" />} title="Triple failure" desc="A bridge in use, a busy boat and a shelter fail at once." onClick={go(() => inject("TRIPLE_FAILURE", {}, "Triple failure injected"))} />
            <MenuItem icon={<Construction className="size-4" />} disabled={!bridge} title={bridge ? `Close ${bname}` : "Close a bridge"} desc={bridge ? "The bridge collapses. Routes over it are re-planned." : "No open bridge left."} onClick={go(() => bridge && inject("CLOSE_EDGE", { edge_id: bridge.id, reason: "bridge collapse" }, `${bname} closed`))} />
            <MenuItem icon={<Ship className="size-4" />} disabled={!boat} title={boat ? `Break down boat ${boat.id}` : "Break down a boat"} desc="Its engine fails. Its rescue is handed to another unit." onClick={go(() => boat && inject("RESOURCE_FAILURE", { resource_id: boat.id, reason: "engine failure" }, `Boat ${boat.id} broke down`))} />
            <MenuItem icon={<Tent className="size-4" />} disabled={!shelter} title={shelter ? `Overflow ${shelter.name}` : "Overflow a shelter"} desc="It suddenly has no free space. People are sent elsewhere." onClick={go(() => shelter && inject("SHELTER_CAPACITY", { shelter_id: shelter.id, capacity: "occupancy", reason: "overflow" }, `${shelter.name} is full`))} />
            <MenuItem icon={<Waves className="size-4" />} title="Flood surge (+0.5 m)" desc="The river jumps half a metre. More roads go under." onClick={go(() => inject("FLOOD_SURGE", { delta: 0.5 }, "Flood surge +0.5 m"))} />
            <MenuItem icon={<Radio className="size-4" />} disabled={!blackout} title={blackout ? `Radio blackout for ${blackout.id}` : "Radio blackout"} desc="A unit loses contact for 15 minutes but keeps its mission." onClick={go(() => blackout && inject("COMM_BLACKOUT", { resource_id: blackout.id, duration: 15 }, `${blackout.id} lost radio contact`))} />
            <MenuItem icon={<Split className="size-4" />} disabled={partitioned || cut.length === 0 || !shelter} title="Split the network" desc="Some boats and a shelter are cut off from everyone else for 30 minutes." onClick={go(() => shelter && inject("NETWORK_PARTITION", { members: [...cut, shelter.id], duration: 30 }, "Network split"))} />
            {extra && <MenuItem icon={<Zap className="size-4" />} disabled={!open} title="Send a contradicting report" desc={open ? `A resident says nobody is at ${open.id}. The system must decide whom to believe.` : "No open request."} onClick={go(() => open && inject("CONTRADICTORY_REPORT", { incident_id: open.id, claim: "NO_VICTIMS", source: "resident" }, `Contradicting report for ${open.id}`))} />}
          </>
  );
}

export function ChaosMenu() {
  return (
    <Dropdown label="Simulate failure" icon={<TriangleAlert className="size-3.5" />} width="w-[360px]">
      {(close) => (
        <>
          <div className="px-3 pt-1.5 pb-1 text-[12px] text-mute">Each option changes the live run. Watch the units re-plan.</div>
          <ChaosItems onDone={close} />
        </>
      )}
    </Dropdown>
  );
}
