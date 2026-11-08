import { memo, useContext, useMemo } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";
import type { Part, PartPin } from "./types";
import { CHIP_W, GUTTER, HEADER_H, NODE_W, ROW_H, chipHeight, pinSide } from "./layout";
import { NetContext, type PinNet } from "./netContext";
import { GateArt, artInfo } from "./GateArt";

export type ChipData = { ref: string; part: Part };
export type ChipNodeType = Node<ChipData, "chip">;

export const KIND_LABEL: Record<string, string> = {
  i: "input", o: "output", t: "3-state output", b: "bidirectional",
  oc: "open-collector output", gnd: "ground", vcc: "power", nc: "no connect",
};

function NetLabel({ info, side, onSelect, selected, value }: {
  info: PinNet | undefined; side: "left" | "right";
  onSelect: (net: string | null) => void; selected: boolean;
  value: number | null | undefined;   // undefined = no simulation running
}) {
  if (!info) return <span className={`netlabel ${side} none`}>—</span>;
  const cls = info.const !== null ? "power" : info.external ? "ext" : "int";
  const pin = info.pin !== null ? ` · P${info.pin}` : "";
  const text = info.external && info.port ? `${info.port}${pin}` : info.label;
  return (
    <button
      type="button"
      className={`netlabel ${side} ${cls}${selected ? " selected" : ""} nodrag`}
      title={`${info.name}${info.external ? " (goes off-chip)" : ""}`}
      onClick={(e) => { e.stopPropagation(); onSelect(selected ? null : info.name); }}
    >
      {value !== undefined && (
        <span className={`vdot ${value === 1 ? "on" : value === 0 ? "off" : "z"}`}
              aria-label={`value ${value ?? "Z"}`} />
      )}
      {text}
    </button>
  );
}

function PinRow({ refName, pin, part, hideName }: {
  refName: string; pin: PartPin; part: Part; hideName: boolean;
}) {
  const { pinNet, issues, selectedNet, select, onPinMenu, netValues } = useContext(NetContext);
  const { side, row } = pinSide(part, pin.number);
  const key = `${refName}.${pin.number}`;
  const info = pinNet[key];
  const issue = issues[key];
  const selected = !!info && info.name === selectedNet;
  const power = pin.kind === "gnd" || pin.kind === "vcc" || pin.kind === "nc";
  return (
    <div
      className={`pinrow ${side}${selected ? " selected" : ""}${issue ? ` issue-${issue}` : ""}`}
      style={{ top: HEADER_H + row * ROW_H, height: ROW_H }}
      title={`${refName} pin ${pin.number}: ${pin.name} (${KIND_LABEL[pin.kind]})` +
             (power ? "" : " — drag to another pin to connect, right-click for options")}
      onContextMenu={(e) => { if (!power) onPinMenu(e, refName, pin.number); }}
      onClick={(e) => { if (info) { e.stopPropagation(); select(info.name); } }}
    >
      <span className={`pinnum kind-${pin.kind}`}>{pin.number}</span>
      {!hideName && <span className="pinname">{pin.name}</span>}
      <NetLabel info={info} side={side} onSelect={select} selected={selected}
                value={netValues && info ? (netValues[info.name] ?? null) : undefined} />
      {!power && (
        <Handle
          type="source"
          id={pin.number}
          position={side === "left" ? Position.Left : Position.Right}
          className={`handle kind-${pin.kind}`}
        />
      )}
    </div>
  );
}

function ChipNodeImpl({ data, selected }: NodeProps<ChipNodeType>) {
  const { ref, part } = data;
  const { onChipMenu, unused, pinNet, selectedNet, netValues } = useContext(NetContext);
  const info = useMemo(() => artInfo(part), [part]);
  const wireClass = (num: string) => {
    const net = pinNet[`${ref}.${num}`];
    if (!net) return "";
    const v = netValues ? netValues[net.name] : undefined;
    return [net.name === selectedNet ? "sel" : "", v === 1 ? "hi" : v === 0 ? "lo" : ""].join(" ");
  };
  return (
    <div className="chip-wrap" style={{ width: NODE_W, paddingLeft: GUTTER }}>
      <div className={`chip${selected ? " chip-selected" : ""}`}
           style={{ width: CHIP_W, height: chipHeight(part) }}>
        <div className="chip-notch" />
        <div className="chip-header" onContextMenu={(e) => onChipMenu(e, ref)}
             title="Drag to move · right-click to rename or delete · Delete key removes">
          <span className="chip-ref">{ref}</span>
          <span className="chip-key">{part.key}</span>
          <div className="chip-title">{part.title}</div>
        </div>
        {part.warning && <div className="chip-warn" title={part.warning}>!</div>}
        {part.units?.length > 0 &&
          <GateArt refName={ref} part={part} unused={unused[ref] ?? []} wireClass={wireClass} />}
        {part.pins.map((p) => <PinRow key={p.number} refName={ref} pin={p} part={part}
                                      hideName={info.hidden.has(p.number)} />)}
      </div>
    </div>
  );
}

export const ChipNode = memo(ChipNodeImpl);
