// Hand-written reference for the TinyTendo U7 (74HC139) + U8/U9 (74HC368)
// merge, written directly from the schematic before cpldglue existed.
// tests/test_generate.py checks the generated design against this file.

module tinytendo_glue (
    // ---- CPU address decode (was U7) ----
    input  wire       m2,
    input  wire       cpu_a13,
    input  wire       cpu_a14,
    input  wire       cpu_a15,
    output wire       wram_ce_n,    // net /WRAM-~{CE}
    output wire       ppu_ce_n,     // net /PPU-~{CE}
    output wire       romsel_n,     // net /~{ROMSEL}

    // ---- PPU A13 inverter (was U8 gate 5) ----
    input  wire       ppu_a13,
    output wire       ppu_a13_n,    // net /PPU-~{A13}

    // ---- Controller ports (were U8, U9) ----
    input  wire       oe1_n,        // net /~{OE1}  ($4016 read)
    input  wire       oe2_n,        // net /~{OE2}  ($4017 read)
    input  wire       p1_d0,        // net /4016-D0
    input  wire       p1_d3,        // net /4016-D3
    input  wire       p1_d4,        // net /4016-D4
    input  wire       p2_d0,        // net /4017-D0
    input  wire       p2_d3,        // net /4017-D3
    input  wire       p2_d4,        // net /4017-D4
    output wire [4:0] cpu_d         // nets /CPU-D0..D4 (3-state, shared bus)
);

    // U7 half B, output O3: M2 = 1, A15 = 1
    assign romsel_n  = ~(m2 & cpu_a15);

    // U7 half B, output O1 (M2 = 1, A15 = 0) enables half A
    wire   lo_half_n = ~(m2 & ~cpu_a15);

    // U7 half A outputs (all high while disabled)
    assign wram_ce_n = lo_half_n | cpu_a14 |  cpu_a13;   // O0: A14=0, A13=0
    assign ppu_ce_n  = lo_half_n | cpu_a14 | ~cpu_a13;   // O1: A14=0, A13=1

    // U8 gate 5: always-enabled inverter
    assign ppu_a13_n = ~ppu_a13;

    // U8/U9: controller reads onto CPU D0-D4
    // /OE1 low:  D0 = ~P1.D0, D1 = 0, D2 = Hi-Z, D3 = ~P1.D3, D4 = ~P1.D4
    // /OE2 low:  D0 = ~P2.D0, D1 = 0, D2 = 0,    D3 = ~P2.D3, D4 = ~P2.D4
    wire rd1 = ~oe1_n;
    wire rd2 = ~oe2_n;

    assign cpu_d[0] = rd1 ? ~p1_d0 : rd2 ? ~p2_d0 : 1'bz;
    assign cpu_d[1] = (rd1 | rd2)   ? 1'b0       : 1'bz;
    assign cpu_d[2] = rd2           ? 1'b0       : 1'bz;
    assign cpu_d[3] = rd1 ? ~p1_d3 : rd2 ? ~p2_d3 : 1'bz;
    assign cpu_d[4] = rd1 ? ~p1_d4 : rd2 ? ~p2_d4 : 1'bz;

endmodule
