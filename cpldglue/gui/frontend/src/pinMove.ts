import type { GenPort } from "./types";

/** Put `signal` on `pin` (as pin locks). A free pin just takes the signal; a
 *  pin another signal is on swaps the two, so both end up locked where the
 *  user put them. `problem(pin, signal)` says why a signal can't go on a pin
 *  (input-only, power, JTAG, ...), or null. */
export function moveSignal(locks: Record<string, number>, ports: GenPort[], signal: string,
                           pin: number, problem: (pin: number, signal: string) => string | null):
    { locks: Record<string, number>; swapped?: string } | { error: string } {
  const port = ports.find((p) => p.name === signal);
  if (!port) return { error: `Unknown signal ${signal}` };
  const from = port.pin;
  if (from === pin) return { locks: { ...locks, [signal]: pin } };
  const why = problem(pin, signal);
  if (why) return { error: why };
  const other = ports.find((p) => p.pin === pin && p.name !== signal);
  if (!other) return { locks: { ...locks, [signal]: pin } };
  if (from == null) {
    // nowhere to send the other signal: let the tool place it again
    const next = { ...locks, [signal]: pin };
    delete next[other.name];
    return { locks: next };
  }
  const back = problem(from, other.name);
  if (back) return { error: `Can't swap with ${other.name}: ${back}` };
  return { locks: { ...locks, [signal]: pin, [other.name]: from }, swapped: other.name };
}
