import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent, MouseEvent as ReactMouseEvent } from "react";
import {
  ReactFlow, ReactFlowProvider, Background, Controls, MiniMap, ConnectionMode,
  applyNodeChanges, useReactFlow,
  type Connection, type Edge, type NodeChange, type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import * as api from "./api";
import * as m from "./model";
import type { Design, DeviceInfo, GenResult, Part } from "./types";
import { ChipNode, KIND_LABEL, type ChipNodeType } from "./ChipNode";
import { NetContext, issuesFromReport, shortNetName, type PinNet } from "./netContext";
import { ReportPanel } from "./ReportPanel";
import { LibraryPanel, PART_MIME } from "./LibraryPanel";
import { NetEditor } from "./NetEditor";
import { ContextMenu, type MenuItem } from "./ContextMenu";
import { NODE_W, findFreeSpot, placeChips } from "./layout";
import { PinoutView } from "./PinoutView";
import { ImportDialog } from "./ImportDialog";
import { BuildDialog } from "./BuildDialog";
import { SetupDialog } from "./SetupDialog";
import { chipSlots } from "./MacrocellBar";

const nodeTypes: NodeTypes = { chip: ChipNode };
const POLL_MS = 2000;

type Menu =
  | { kind: "pin"; x: number; y: number; ref: string; pin: string }
  | { kind: "chip"; x: number; y: number; ref: string };

export default function App() {
  return (
    <ReactFlowProvider>
      <Editor />
    </ReactFlowProvider>
  );
}

function Editor() {
  const flow = useReactFlow();
  const [partList, setPartList] = useState<Part[]>([]);
  const parts = useMemo(() => Object.fromEntries(partList.map((p) => [p.key, p])), [partList]);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);

  const [hist, setHist] = useState<m.History>(() => m.historyInit(m.emptyDesign()));
  const histRef = useRef(hist);
  histRef.current = hist;
  const design = hist.present;

  const [path, setPath] = useState("");
  const [loaded, setLoaded] = useState(false);
  const baseMtime = useRef(-1);
  const [savedJson, setSavedJson] = useState("");
  const [diskChanged, setDiskChanged] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [flash, setFlash] = useState("");
  const [saving, setSaving] = useState(false);

  const [gen, setGen] = useState<GenResult | null>(null);
  const [genError, setGenError] = useState("");
  const [selectedNet, setSelectedNet] = useState<string | null>(null);
  const [menu, setMenu] = useState<Menu | null>(null);
  const [showWires, setShowWires] = useState(false);
  const [view, setView] = useState<"chips" | "pinout">("chips");
  const [simNets, setSimNets] = useState<Record<string, number | null> | null>(null);
  const [dialog, setDialog] = useState<"import" | "build" | "setup" | null>(null);
  // Other panels (e.g. the simulator's "Yosys not found") can ask for Setup.
  useEffect(() => {
    const open = () => setDialog("setup");
    window.addEventListener("cpldglue:setup", open);
    return () => window.removeEventListener("cpldglue:setup", open);
  }, []);
  const [help, setHelp] = useState(false);
  const [buildCfg, setBuildCfg] = useState<api.BuildConfig | null>(null);

  const dirty = loaded && JSON.stringify(design) !== savedJson;
  const dirtyRef = useRef(dirty);
  dirtyRef.current = dirty;

  // ---- loading --------------------------------------------------------
  useEffect(() => {
    api.getParts().then(setPartList).catch((e) => setLoadError(String(e)));
    api.getDevices().then(setDevices).catch(() => {});
  }, []);

  const adopt = useCallback((d: Design, mtime: number) => {
    baseMtime.current = mtime;
    setHist(m.historyInit(d));
    setSavedJson(JSON.stringify(d));
    setDiskChanged(false);
    setLoaded(true);
  }, []);

  const poll = useCallback(async (force = false) => {
    try {
      const p = await api.getProject();
      setPath(p.path);
      setLoadError(p.error ? `Could not load project: ${p.error}` : "");
      if (p.error) return;
      if (force || baseMtime.current === -1) { adopt(p.design, p.mtime); return; }
      if (p.mtime !== baseMtime.current) {
        if (dirtyRef.current) setDiskChanged(true);   // ask before discarding edits
        else adopt(p.design, p.mtime);
      }
    } catch (e) {
      setLoadError(`Lost contact with the cpldglue server (${e})`);
    }
  }, [adopt]);

  useEffect(() => {
    poll();
    const id = setInterval(() => poll(), POLL_MS);
    return () => clearInterval(id);
  }, [poll]);

  // Whether the Build button is available (depends on the device's fitter).
  useEffect(() => {
    if (!loaded) return;
    api.buildConfig(histRef.current.present).then(setBuildCfg).catch(() => setBuildCfg(null));
  }, [loaded, design.device]);

  // Regenerate on every change (debounced).
  useEffect(() => {
    if (!loaded) return;
    let stale = false;
    const t = setTimeout(() => {
      api.generate(design)
        .then((g) => { if (!stale) { setGen(g); setGenError(""); } })
        .catch((e) => { if (!stale) setGenError(String(e)); });
    }, 150);
    return () => { stale = true; clearTimeout(t); };
  }, [design, loaded]);

  useEffect(() => {
    if (!flash) return;
    const t = setTimeout(() => setFlash(""), 4000);
    return () => clearTimeout(t);
  }, [flash]);

  // ---- editing ----------------------------------------------------------
  const apply = useCallback((fn: (d: Design) => Design) => {
    try {
      const h = histRef.current;
      const next = fn(h.present);
      if (next !== h.present) setHist(m.historyPush(h, next));
    } catch (e) {
      setFlash(e instanceof Error ? e.message : String(e));
    }
  }, []);

  const undo = useCallback(() => setHist((h) => m.historyUndo(h)), []);
  const redo = useCallback(() => setHist((h) => m.historyRedo(h)), []);

  // ---- open / save as (native dialogs in the desktop app) ----------------
  const [recent, setRecent] = useState<string[]>([]);
  useEffect(() => {
    if (!path) return;
    api.getProject().then((p) => setRecent(p.recent ?? [])).catch(() => {});
    const file = path.split(/[\\/]/).pop() ?? path;
    api.setTitle(`${file} — CPLD-Builder`);
  }, [path]);

  const openPath = useCallback(async (p: string | null) => {
    if (!p) return;
    if (dirtyRef.current && !window.confirm("Discard unsaved changes to this project?")) return;
    try {
      await api.openProject(p);
      baseMtime.current = -1;
      await poll(true);
    } catch (e) { setFlash(`Could not open: ${e instanceof Error ? e.message : e}`); }
  }, [poll]);

  const saveAs = useCallback(async () => {
    const p = await api.pickPath("save", path);
    if (!p) return;
    try {
      const d = histRef.current.present;
      const info = await api.saveProjectAs(p, d);
      setPath(info.path);
      adopt(d, info.mtime);
      setFlash("Saved");
    } catch (e) { setFlash(`Save failed: ${e instanceof Error ? e.message : e}`); }
  }, [path, adopt]);

  const save = useCallback(async (force = false) => {
    setSaving(true);
    try {
      const d = histRef.current.present;
      const res = await api.saveProject(d, baseMtime.current, force);
      if (res.conflict) { setDiskChanged(true); return; }
      baseMtime.current = res.mtime;
      setSavedJson(JSON.stringify(d));
      setDiskChanged(false);
      setFlash("Saved");
    } catch (e) {
      setFlash(`Save failed: ${e instanceof Error ? e.message : e}`);
    } finally {
      setSaving(false);
    }
  }, []);

  const addPartAt = useCallback((key: string, pos?: { x: number; y: number }) => {
    const p = pos ?? flow.screenToFlowPosition({
      x: window.innerWidth / 2, y: window.innerHeight / 2,
    });
    apply((d) => {
      const part = parts[key];
      const start = { x: p.x - NODE_W / 2, y: p.y - 60 };
      return m.addPart(d, key, part ? findFreeSpot(d, parts, part, start) : start);
    });
  }, [apply, flow, parts]);

  // Keyboard shortcuts
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = t && (t.tagName === "INPUT" || t.tagName === "SELECT" ||
                           t.tagName === "TEXTAREA" || t.isContentEditable);
      const mod = e.ctrlKey || e.metaKey;
      if (mod && e.key.toLowerCase() === "s") { e.preventDefault(); save(); return; }
      if (typing) return;
      if (mod && e.key.toLowerCase() === "z" && !e.shiftKey) { e.preventDefault(); undo(); }
      else if (mod && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
        e.preventDefault(); redo();
      } else if ((e.key === "Delete" || e.key === "Backspace") && selectedNet &&
                 !nodesRef.current.some((n) => n.selected)) {
        e.preventDefault();
        const n = selectedNet;
        setSelectedNet(null);
        apply((d) => m.deleteNet(d, n));
      } else if (e.key === "Escape") {
        setSelectedNet(null); setMenu(null); setHelp(false);
      } else if (e.key === "?") {
        setHelp((h) => !h);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [apply, redo, save, selectedNet, undo]);

  // Warn before closing with unsaved edits.
  useEffect(() => {
    const h = (e: BeforeUnloadEvent) => { if (dirtyRef.current) e.preventDefault(); };
    window.addEventListener("beforeunload", h);
    return () => window.removeEventListener("beforeunload", h);
  }, []);

  // Drop a selection that no longer exists (after undo, rename...).
  useEffect(() => {
    if (selectedNet && !design.nets[selectedNet]) setSelectedNet(null);
  }, [design, selectedNet]);

  // ---- derived view state -------------------------------------------------
  const pinNet = useMemo(() => {
    const out: Record<string, PinNet> = {};
    for (const net of Object.values(design.nets)) {
      const g = gen?.nets[net.name];
      const info: PinNet = {
        name: net.name,
        label: net.const !== null ? (net.const ? "VCC" : "GND") : shortNetName(net.name),
        external: net.external, const: net.const,
        port: g?.port ?? null, pin: g?.pin ?? null,
      };
      for (const n of net.nodes) out[`${n.ref}.${n.pin}`] = info;
    }
    return out;
  }, [design, gen]);

  const issues = useMemo(() => issuesFromReport(gen?.errors ?? [], gen?.warnings ?? []),
                         [gen]);

  const [nodes, setNodes] = useState<ChipNodeType[]>([]);
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  useEffect(() => {
    if (!partList.length) return;
    const pos = placeChips(design, parts);
    setNodes((old) => {
      const sel = new Set(old.filter((n) => n.selected).map((n) => n.id));
      return Object.entries(design.parts)
        .filter(([, key]) => parts[key])
        .map(([ref, key]) => ({
          id: ref, type: "chip" as const,
          position: { x: pos[ref].x, y: pos[ref].y },
          data: { ref, part: parts[key] },
          selected: sel.has(ref),
          dragHandle: ".chip-header",
        }));
    });
  }, [design, parts, partList.length]);

  const edges: Edge[] = useMemo(() => {
    if (!showWires) return [];
    const out: Edge[] = [];
    for (const net of Object.values(design.nets)) {
      if (net.const !== null) continue;
      net.nodes.slice(1).forEach((n, i) => {
        const a = net.nodes[0];
        out.push({
          id: `${net.name}|${i}`, source: a.ref, sourceHandle: a.pin,
          target: n.ref, targetHandle: n.pin, data: { net: net.name },
          className: `wire${net.external ? " ext" : ""}${net.name === selectedNet ? " selected" : ""}`,
        });
      });
    }
    return out;
  }, [design, showWires, selectedNet]);

  const onNodesChange = useCallback((changes: NodeChange<ChipNodeType>[]) => {
    // Selecting a chip ends net selection, so Delete means "delete the chip".
    if (changes.some((c) => c.type === "select" && c.selected)) setSelectedNet(null);
    setNodes((ns) => applyNodeChanges(changes, ns));
  }, []);

  const onConnect = useCallback((c: Connection) => {
    if (!c.source || !c.target || !c.sourceHandle || !c.targetHandle) return;
    const a = { ref: c.source, pin: c.sourceHandle };
    const b = { ref: c.target, pin: c.targetHandle };
    apply((d) => m.connect(d, a, b));
    const after = m.connect(histRef.current.present, a, b);
    const net = m.netOfPin(after, a.ref, a.pin);
    if (net) setSelectedNet(net.name);
  }, [apply]);

  const onDrop = useCallback((e: DragEvent) => {
    const key = e.dataTransfer.getData(PART_MIME);
    if (!key) return;
    e.preventDefault();
    addPartAt(key, flow.screenToFlowPosition({ x: e.clientX, y: e.clientY }));
  }, [addPartAt, flow]);

  const menuItems = (mn: Menu): { title: string; items: MenuItem[] } => {
    if (mn.kind === "chip") {
      return {
        title: `${mn.ref} (${design.parts[mn.ref]})`,
        items: [
          { label: "Rename…", onClick: () => {
              const to = window.prompt(`New reference for ${mn.ref}`, mn.ref);
              if (to && to !== mn.ref) apply((d) => m.renamePart(d, mn.ref, to.trim()));
            } },
          { label: "Delete chip", danger: true, onClick: () => apply((d) => m.removePart(d, mn.ref)) },
        ],
      };
    }
    const part = parts[design.parts[mn.ref]];
    const pin = part?.pins.find((p) => p.number === mn.pin);
    const net = m.netOfPin(design, mn.ref, mn.pin);
    const suggested = `${mn.ref}_${pin?.name ?? mn.pin}`;
    return {
      title: `${mn.ref} pin ${mn.pin}: ${pin?.name} (${pin ? KIND_LABEL[pin.kind] : "?"})`,
      items: [
        { label: net?.external ? "Already a CPLD pin" : "Make it a CPLD pin (off-chip)",
          disabled: !!net?.external || net?.const != null,
          onClick: () => {
            apply((d) => m.makeExternal(d, mn.ref, mn.pin, suggested));
            const n = m.netOfPin(m.makeExternal(design, mn.ref, mn.pin, suggested), mn.ref, mn.pin);
            if (n) setSelectedNet(n.name);
          } },
        { label: "Tie low (GND)", onClick: () => apply((d) => m.tiePin(d, mn.ref, mn.pin, 0)) },
        { label: "Tie high (VCC)", onClick: () => apply((d) => m.tiePin(d, mn.ref, mn.pin, 1)) },
        { label: "Select net", disabled: !net, onClick: () => net && setSelectedNet(net.name) },
        { label: "Disconnect", danger: true, disabled: !net,
          onClick: () => apply((d) => m.disconnectPin(d, mn.ref, mn.pin)) },
      ],
    };
  };

  // Chip colors persist for the session (see chipSlots).
  const slotMemo = useRef<Record<string, number>>({});
  const slots = useMemo(() => {
    const s = chipSlots(design, slotMemo.current);
    slotMemo.current = s;
    return s;
  }, [design]);
  const chipMacrocells = useMemo(() => {
    const parts = gen?.macrocells?.parts ?? {};
    return Object.fromEntries(Object.entries(parts).map(([ref, v]) =>
      [ref, { estimate: v.estimate, slot: slots[ref] ?? 0 }]));
  }, [gen, slots]);

  const netCtx = useMemo(() => ({
    pinNet, issues, selectedNet, select: setSelectedNet, netValues: simNets,
    unused: gen?.unused ?? {},
    macrocells: chipMacrocells,
    onPinMenu: (e: ReactMouseEvent, ref: string, pin: string) => {
      e.preventDefault(); e.stopPropagation();
      setMenu({ kind: "pin", x: e.clientX, y: e.clientY, ref, pin });
    },
    onChipMenu: (e: ReactMouseEvent, ref: string) => {
      e.preventDefault(); e.stopPropagation();
      setMenu({ kind: "chip", x: e.clientX, y: e.clientY, ref });
    },
  }), [pinNet, issues, selectedNet, simNets, gen?.unused, chipMacrocells]);

  const deviceNames = [...new Set(devices.map((d) => d.device))];
  const packages = devices.filter((d) => d.device === design.device).map((d) => d.package);
  const mi = menu ? menuItems(menu) : null;
  const deviceInfo = devices.find((x) => x.device === design.device && x.package === design.package);

  const importDesign = (imported: Design) => {
    apply((d) => ({ ...imported, layout: {}, pin_locks: { ...d.pin_locks } }));
    setDialog(null);
    setSelectedNet(null);
    setView("chips");
    setTimeout(() => flow.fitView({ padding: 0.15, duration: 300 }), 100);
  };

  return (
    <div className="app">
      <header className="topbar">
        <strong className="brand">cpldglue</strong>
        <button onClick={async () => openPath(await api.pickPath("open", path))}
                title="Open another project, or type a new file name to start one">Open…</button>
        {recent.length > 0 && (
          <select aria-label="Recent projects" value="" className="recent"
                  onChange={(e) => openPath(e.target.value || null)}>
            <option value="">Recent</option>
            {recent.map((r) => <option key={r} value={r}>{r.split(/[\\/]/).pop()} — {r}</option>)}
          </select>
        )}
        <button onClick={saveAs} title="Save the project under a new name">Save as…</button>
        <NameField value={design.name}
                   onCommit={(v) => apply((d) => m.setDesignField(d, "name", v))} />
        <select aria-label="Device" value={design.device}
                onChange={(e) => {
                  const dev = e.target.value;
                  apply((d) => {
                    let n = m.setDesignField(d, "device", dev);
                    const pk = devices.filter((x) => x.device === dev).map((x) => x.package);
                    if (pk.length && !pk.includes(n.package)) n = m.setDesignField(n, "package", pk[0]);
                    return n;
                  });
                }}>
          {(deviceNames.includes(design.device) ? deviceNames : [design.device, ...deviceNames]).map((d) => {
            const info = devices.find((x) => x.device === d);
            return <option key={d} value={d}>
              {info ? `${d} · ${info.macrocells} MC${info.vcc !== undefined && info.vcc < 5 ? " · 3.3 V" : ""}` : d}
            </option>;
          })}
        </select>
        <select aria-label="Package" value={design.package}
                onChange={(e) => apply((d) => m.setDesignField(d, "package", e.target.value))}>
          {(packages.includes(design.package) ? packages : [design.package, ...packages]).map((p) => <option key={p}>{p}</option>)}
        </select>
        <label className="small" title="Keep the 4 JTAG pins for in-circuit programming">
          <input type="checkbox" checked={design.keep_jtag}
                 onChange={(e) => apply((d) => m.setDesignField(d, "keep_jtag", e.target.checked))} />
          {" "}JTAG
        </label>
        <span className="sep" />
        <div className="segmented" role="tablist" aria-label="View">
          <button role="tab" aria-selected={view === "chips"} className={view === "chips" ? "on" : ""}
                  onClick={() => setView("chips")}>Chips</button>
          <button role="tab" aria-selected={view === "pinout"} className={view === "pinout" ? "on" : ""}
                  onClick={() => setView("pinout")}>Pinout</button>
        </div>
        <span className="sep" />
        <button onClick={undo} disabled={!hist.past.length} title="Undo (Ctrl+Z)">Undo</button>
        <button onClick={redo} disabled={!hist.future.length} title="Redo (Ctrl+Y)">Redo</button>
        <button title="Clear saved positions and lay the chips out in a grid"
                disabled={!Object.keys(design.layout ?? {}).length}
                onClick={() => {
                  apply((d) => ({ ...d, layout: {} }));
                  setTimeout(() => flow.fitView({ padding: 0.15, duration: 300 }), 50);
                }}>Tidy</button>
        <label className="small" title="Draw wires between connected pins">
          <input type="checkbox" checked={showWires} onChange={(e) => setShowWires(e.target.checked)} />
          {" "}Wires
        </label>
        <span className="spacer" />
        <button onClick={() => setDialog("import")} title="Pick chips from a KiCad schematic">
          Import KiCad…
        </button>
        {buildCfg?.enabled && (
          <button title="Run Yosys and the Microchip fitter"
                  onClick={async () => {
                    try { setBuildCfg(await api.buildConfig(design)); } catch { /* keep old */ }
                    setDialog("build");
                  }}>
            Build…
          </button>
        )}
        <button onClick={() => setDialog("setup")}
                title="Yosys, the Microchip fitter and other optional tools">Setup…</button>
        <span className="path muted" title={path}>{path}</span>
        <button className="iconbtn" onClick={() => setHelp(true)} title="Shortcuts (?)"
                aria-label="Shortcuts">?</button>
        <button className={`primary${dirty ? " dirty" : ""}`} onClick={() => save()}
                disabled={saving || !loaded} title="Save (Ctrl+S)" data-testid="save">
          {dirty ? "Save •" : "Saved"}
        </button>
      </header>

      {loadError && <div className="banner error">{loadError}</div>}
      {diskChanged && (
        <div className="banner warning">
          The project file changed on disk while you have unsaved edits.
          <button onClick={() => poll(true)}>Load the file (discard my edits)</button>
          <button onClick={() => save(true)}>Overwrite it with my version</button>
        </div>
      )}

      <main className={`workspace${view === "chips" ? "" : " no-lib"}`}>
        {view === "chips" && <LibraryPanel parts={partList} onAdd={(k) => addPartAt(k)} />}
        <div className={`canvas${view === "chips" ? "" : " hidden"}`} data-testid="canvas"
             onDragOver={(e) => { if (e.dataTransfer.types.includes(PART_MIME)) e.preventDefault(); }}
             onDrop={onDrop}>
          <NetContext.Provider value={netCtx}>
            <ReactFlow
              nodes={nodes}
              edges={edges}
              nodeTypes={nodeTypes}
              onNodesChange={onNodesChange}
              onNodeDragStop={(_, node) => apply((d) => m.movePart(d, node.id, node.position))}
              onNodesDelete={(del) => apply((d) => del.reduce((acc, n) => m.removePart(acc, n.id), d))}
              onConnect={onConnect}
              onEdgeClick={(_, edge) => setSelectedNet((edge.data?.net as string) ?? null)}
              connectionMode={ConnectionMode.Loose}
              deleteKeyCode={["Delete", "Backspace"]}
              fitView
              fitViewOptions={{ padding: 0.15 }}
              minZoom={0.15}
              onPaneClick={() => { setSelectedNet(null); setMenu(null); }}
              proOptions={{ hideAttribution: true }}
            >
              <Background gap={20} />
              <Controls showInteractive={false} />
              <MiniMap pannable zoomable nodeColor="#7d8696" nodeStrokeColor="#7d8696"
                       maskColor="rgba(120,130,150,0.18)" />
            </ReactFlow>
          </NetContext.Provider>
          {loaded && !Object.keys(design.parts).length && (
            <div className="empty-hint">
              Drag a part from the library to start, then drag between pins to wire them.
              Or use “Import KiCad…” to pull chips from a schematic. Press ? for shortcuts.
            </div>
          )}
          {selectedNet && design.nets[selectedNet] && (
            <NetEditor
              design={design} gen={gen} name={selectedNet}
              onRename={(to) => {
                apply((d) => m.renameNet(d, selectedNet, to));
                if (!m.validNetName(to) && !(to in design.nets)) setSelectedNet(to);
              }}
              onExternal={(v) => apply((d) => m.setExternal(d, selectedNet, v))}
              onConst={(v) => apply((d) => m.setConst(d, selectedNet, v))}
              onDisconnect={(ref, pin) => apply((d) => m.disconnectPin(d, ref, pin))}
              onDelete={() => { const n = selectedNet; setSelectedNet(null); apply((d) => m.deleteNet(d, n)); }}
              onClose={() => setSelectedNet(null)}
            />
          )}
          {flash && view === "chips" && <div className="flash" role="status">{flash}</div>}
        </div>
        {view === "pinout" && (
          <div className="canvas">
            <PinoutView
              design={design} device={deviceInfo} gen={gen}
              selectedNet={selectedNet} onSelectNet={setSelectedNet}
              onLock={(s, p) => apply((d) => m.lockPin(d, s, p))}
              onUnlock={(s) => apply((d) => m.unlockPin(d, s))}
              onSetLocks={(l) => apply((d) => m.setLocks(d, l))}
              onFlash={setFlash}
            />
            {flash && <div className="flash" role="status">{flash}</div>}
          </div>
        )}
        <ReportPanel design={design} gen={gen} genError={genError} slots={slots}
                     selectedNet={selectedNet} onSelectNet={setSelectedNet}
                     onSimNets={setSimNets} />
      </main>

      {help && (
        <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setHelp(false); }}>
          <div className="modal help" role="dialog" aria-modal="true" aria-label="Shortcuts">
            <div className="modal-head"><h2>Shortcuts and gestures</h2>
              <button className="iconbtn" onClick={() => setHelp(false)} aria-label="Close">×</button></div>
            <table className="keys"><tbody>
              {[
                ["Drag pin → pin", "connect (joins nets)"],
                ["Click a net label", "select the net: rename, off-chip, constant, delete"],
                ["Right-click a pin", "make CPLD pin, tie high/low, disconnect"],
                ["Right-click a chip header", "rename or delete the chip"],
                ["Drag a chip header", "move it"],
                ["Delete / Backspace", "delete the selected chip or net"],
                ["Ctrl+Z / Ctrl+Y", "undo / redo"],
                ["Ctrl+S", "save"],
                ["Esc", "clear selection, close menus"],
                ["Pinout view", "drag a signal onto a pin, or select it and click a free pin"],
                ["?", "this help"],
              ].map(([k, v]) => <tr key={k}><td className="mono">{k}</td><td>{v}</td></tr>)}
            </tbody></table>
          </div>
        </div>
      )}
      {dialog === "import" && (
        <ImportDialog design={design} parts={partList} onImport={importDesign}
                      onClose={() => setDialog(null)} />
      )}
      {dialog === "setup" && <SetupDialog onClose={() => setDialog(null)} />}
      {dialog === "build" && buildCfg && (
        <BuildDialog design={design} config={buildCfg} onClose={() => setDialog(null)}
                     onSetup={() => setDialog("setup")} />
      )}
      {menu && mi && (
        <ContextMenu x={menu.x} y={menu.y} title={mi.title} items={mi.items}
                     onClose={() => setMenu(null)} />
      )}
    </div>
  );
}

/** Text field that commits on Enter / blur, so a rename is one undo step. */
function NameField({ value, onCommit }: { value: string; onCommit: (v: string) => void }) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    const v = draft.trim();
    if (v && v !== value) onCommit(v); else setDraft(value);
  };
  return (
    <input className="design-name mono" aria-label="Design name" value={draft}
           onChange={(e) => setDraft(e.target.value)} onBlur={commit}
           onKeyDown={(e) => {
             if (e.key === "Enter") (e.target as HTMLInputElement).blur();
             if (e.key === "Escape") { setDraft(value); (e.target as HTMLInputElement).blur(); }
           }} />
  );
}
