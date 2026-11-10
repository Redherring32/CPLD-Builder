import type { Design, DeviceInfo, GenResult, Part, ProjectInfo } from "./types";

async function json<T>(res: Response): Promise<T> {
  const body = await res.json();
  if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
  return body as T;
}

export async function getParts(): Promise<Part[]> {
  return (await json<{ parts: Part[] }>(await fetch("api/parts"))).parts;
}

export async function getDevices(): Promise<DeviceInfo[]> {
  return (await json<{ devices: DeviceInfo[] }>(await fetch("api/devices"))).devices;
}

export async function getProject(): Promise<ProjectInfo> {
  return json<ProjectInfo>(await fetch("api/project"));
}

export async function generate(design: Design): Promise<GenResult> {
  return json<GenResult>(
    await fetch("api/generate", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ design }),
    }),
  );
}

export type SaveResult = { conflict: boolean; mtime: number };

export async function saveProject(design: Design, baseMtime: number,
                                  force = false): Promise<SaveResult> {
  const res = await fetch("api/project", {
    method: "PUT",
    headers: JSON_HEADERS,
    body: JSON.stringify({ design, base_mtime: baseMtime, force }),
  });
  const body = await res.json();
  if (res.status === 409) return body as SaveResult;
  if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
  return body as SaveResult;
}

export interface SimPort { name: string; direction: "input" | "output" | "inout"; net: string }
export interface SimState {
  ok: boolean;
  error?: string;
  values: Record<string, number | null>;
  nets: Record<string, number | null>;
  contention: boolean;
  trace?: Record<string, number | null>[];
}
export interface SimBuild extends SimState { ports: SimPort[] }

export async function simBuild(design: Design, fresh = false): Promise<SimBuild> {
  const res = await fetch("api/sim/build", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ design, fresh }),
  });
  return (await res.json()) as SimBuild;
}

export async function simStep(steps: Record<string, number | null>[]): Promise<SimState> {
  return json<SimState>(await fetch("api/sim/step", {
    method: "POST", headers: JSON_HEADERS,
    body: JSON.stringify({ steps }),
  }));
}

// ---- KiCad import ----
export interface KiComponent {
  ref: string; value: string; part: string | null;
  alternatives?: string[];       // chips driving the same nets: fit one or the other
}
export interface KiAlternatives { refs: string[]; nets: string[] }
export interface KiPreview {
  pins: number; capacity: number | null; errors: string[]; warnings: string[]; design: Design;
}

/** Every write request carries X-Cpldglue, which a web page on another site
 *  can't add without a CORS preflight the server never approves. */
const JSON_HEADERS = { "Content-Type": "application/json", "X-Cpldglue": "1" };

async function post<T>(url: string, body: unknown): Promise<T> {
  return json<T>(await fetch(url, {
    method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body),
  }));
}

/** The desktop app's native file dialog, filtered to KiCad files; null in a
 *  plain browser (use the in-app FileBrowser there). */
export function nativeKicadPicker(): ((current: string) => Promise<string | null>) | null {
  const b = bridge();
  return b ? (current) => b.pick("kicad", current) : null;
}
export interface DirListing {
  path: string; parent: string | null; dirs: string[]; files: string[]; roots: string[]; sep: string;
}
export function listDir(path: string) {
  return post<DirListing>("api/fs/list", { path });
}

export async function kicadFind(): Promise<string[]> {
  return (await json<{ files: string[] }>(await fetch("api/kicad/find"))).files;
}

export function kicadComponents(path: string) {
  return post<{ path: string; components: KiComponent[]; alternatives?: KiAlternatives[] }>(
    "api/kicad/components", { path });
}

export function kicadPreview(path: string, refs: string[], overrides: Record<string, string>,
                             design: Design, variants?: Record<string, string[]>) {
  return post<KiPreview>("api/kicad/preview", { path, refs, overrides, design, variants });
}

// ---- Build ----
export interface BuildConfig {
  enabled: boolean; flow_ok: boolean; flow_dir: string | null; fitter: string | null;
  nextpnr?: string | null; quartus?: string | null;
}
export function buildConfig(design: Design) {
  return post<BuildConfig>("api/build/config", { design });
}
export interface DepInfo {
  id: string; title: string; found: boolean; where: string | null;
  needed_for: string; download: string; can_fetch: boolean;
  installer?: string | null; url?: string;
}
export interface DepJob { state: "running" | "done" | "error"; done: number; total: number | null; message: string }
export async function deps() {
  return json<{ deps: DepInfo[]; jobs: Record<string, DepJob> }>(await fetch("api/deps"));
}
export function fetchDep(id: string) {
  return post<DepJob>("api/deps/fetch", { id });
}
export function openInstaller() {
  return post<{ ok: boolean }>("api/deps/installer", {});
}
export function openProject(path: string) {
  return post<ProjectInfo>("api/project/open", { path });
}
export interface ExampleInfo { id: string; title: string }
export async function getExamples(): Promise<ExampleInfo[]> {
  return (await json<{ examples: ExampleInfo[] }>(await fetch("api/examples"))).examples;
}
export function openExample(id: string) {
  return post<ProjectInfo>("api/project/example", { id });
}
export function saveProjectAs(path: string, design: Design) {
  return post<ProjectInfo>("api/project/saveas", { path, design });
}

/** The desktop app (pywebview) exposes native file dialogs and the window
 *  title; in a plain browser these fall back to a prompt / document.title. */
type Bridge = { pick: (mode: "open" | "save" | "kicad", current: string) => Promise<string | null>;
                title: (t: string) => Promise<void>;
                copy: (text: string) => Promise<boolean> };
function bridge(): Bridge | null {
  const w = window as unknown as { pywebview?: { api?: Bridge } };
  return w.pywebview?.api?.pick ? w.pywebview.api : null;
}
export async function pickPath(mode: "open" | "save", current: string): Promise<string | null> {
  const b = bridge();
  if (b) return b.pick(mode, current);
  const p = window.prompt(mode === "open"
    ? "Path of the project to open (.cg or .json; a new name starts an empty project):"
    : "Save the project as (.cg or .json):", current);
  return p && p.trim() ? p.trim() : null;
}
let lastTitle = "";
export function setTitle(t: string) {
  lastTitle = t;
  document.title = t;
  bridge()?.title(t).catch(() => {});
}
// The desktop bridge appears a moment after the page loads.
if (typeof window !== "undefined")
  window.addEventListener("pywebviewready", () => { if (lastTitle) setTitle(lastTitle); });

export interface GreenPakBitstream {
  ok: boolean; errors: string[]; notes?: string[]; check: string; placement?: string[];
  files?: { txt: string; ino: string; bin: string; mask: string };
}
export interface GreenPakResult {
  ok: boolean; error?: string; fits: boolean; notes: string[]; unplaced: string[];
  cells: { type: string; title: string; used: number; total: number }[];
  luts: number; flops: number; oe: number; sheet: string;
  bitstream?: GreenPakBitstream | null;
}
export function greenpak(design: Design) {
  return post<GreenPakResult>("api/greenpak", { design });
}

export interface GalCell {
  pin: number; name: string; kind: "reg" | "comb" | "input" | "unused";
  terms: number; capacity: number; oe: boolean; active_high: boolean; what: string;
}
export interface GalResult {
  ok: boolean; error?: string; fits: boolean; errors: string[]; notes: string[];
  mode: string; mode_title: string; cells: GalCell[]; pins: Record<string, number>;
  check: string; check_ok: boolean; pld: string;
}
export function galFit(design: Design) {
  return post<GalResult>("api/gal", { design });
}

export interface KicadSymbol { name: string; clipboard: string; library: string; warnings: string[]; labels: number }
export function kicadSymbol(design: Design) {
  return post<KicadSymbol>("api/kicad/symbol", { design });
}

/** Copy text: the page's clipboard API, else the desktop app's, else false. */
export async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch { /* blocked (e.g. Qt WebEngine): try the app bridge */ }
  const b = bridge();
  if (b?.copy) {
    try { if (await b.copy(text)) return true; } catch { /* fall through */ }
  }
  return false;
}

export function runBuild(design: Design) {
  return post<{ ok: boolean; log: string; outdir?: string }>("api/build", { design });
}
