// cpldglue chip models
//
// One module per part, named cg_<part>. Port names are listed per pin in
// cpldglue/chips.py, which is the single source of truth for pinouts.
//
// Conventions (so the generator can merge chips inside one CPLD):
//   * Everything here is plain 2-valued logic. No 1'bz inside models.
//   * A 3-state output pin X has two ports: X (data) and X_oe (1 = driving).
//   * A bidirectional pin X has three ports: X_i (what the pin reads),
//     X_o (data driven) and X_oe (1 = driving).
//   * An open-collector output X is a plain output; the generator turns
//     X = 0 into "pull low" and X = 1 into "release".
//   * Asynchronous parallel loads (74x165, CD4021) are written as per-bit
//     async set/reset so they map onto ATF15xx macrocell AP/AR terms.
//
// Verilog-2001, no vendor primitives.

// ===========================================================================
// Gates
// ===========================================================================

// Quad 2-input NAND / NOR / AND / OR / XOR
module cg_74x00 (input a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = ~(a1 & b1); assign y2 = ~(a2 & b2);
    assign y3 = ~(a3 & b3); assign y4 = ~(a4 & b4);
endmodule

module cg_74x02 (input a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = ~(a1 | b1); assign y2 = ~(a2 | b2);
    assign y3 = ~(a3 | b3); assign y4 = ~(a4 | b4);
endmodule

module cg_74x08 (input a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = a1 & b1; assign y2 = a2 & b2;
    assign y3 = a3 & b3; assign y4 = a4 & b4;
endmodule

module cg_74x32 (input a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = a1 | b1; assign y2 = a2 | b2;
    assign y3 = a3 | b3; assign y4 = a4 | b4;
endmodule

module cg_74x86 (input a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = a1 ^ b1; assign y2 = a2 ^ b2;
    assign y3 = a3 ^ b3; assign y4 = a4 ^ b4;
endmodule

// Hex inverter (also used for 74x14 and the open-collector 74x05/06)
module cg_74x04 (input a1,a2,a3,a4,a5,a6, output y1,y2,y3,y4,y5,y6);
    assign y1 = ~a1; assign y2 = ~a2; assign y3 = ~a3;
    assign y4 = ~a4; assign y5 = ~a5; assign y6 = ~a6;
endmodule

// Hex buffer (open-collector 74x07)
module cg_74x07 (input a1,a2,a3,a4,a5,a6, output y1,y2,y3,y4,y5,y6);
    assign y1 = a1; assign y2 = a2; assign y3 = a3;
    assign y4 = a4; assign y5 = a5; assign y6 = a6;
endmodule

// Triple 3-input NAND / AND
module cg_74x10 (input a1,b1,c1,a2,b2,c2,a3,b3,c3, output y1,y2,y3);
    assign y1 = ~(a1 & b1 & c1); assign y2 = ~(a2 & b2 & c2);
    assign y3 = ~(a3 & b3 & c3);
endmodule

module cg_74x11 (input a1,b1,c1,a2,b2,c2,a3,b3,c3, output y1,y2,y3);
    assign y1 = a1 & b1 & c1; assign y2 = a2 & b2 & c2;
    assign y3 = a3 & b3 & c3;
endmodule

// Dual 4-input NAND
module cg_74x20 (input a1,b1,c1,d1,a2,b2,c2,d2, output y1,y2);
    assign y1 = ~(a1 & b1 & c1 & d1);
    assign y2 = ~(a2 & b2 & c2 & d2);
endmodule

// ===========================================================================
// 3-state buffers
// ===========================================================================

// Quad buffer, active-low enables
module cg_74x125 (input oe1_n,a1,oe2_n,a2,oe3_n,a3,oe4_n,a4,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe);
    assign y1 = a1; assign y1_oe = ~oe1_n;
    assign y2 = a2; assign y2_oe = ~oe2_n;
    assign y3 = a3; assign y3_oe = ~oe3_n;
    assign y4 = a4; assign y4_oe = ~oe4_n;
endmodule

// Quad buffer, active-high enables
module cg_74x126 (input oe1,a1,oe2,a2,oe3,a3,oe4,a4,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe);
    assign y1 = a1; assign y1_oe = oe1;
    assign y2 = a2; assign y2_oe = oe2;
    assign y3 = a3; assign y3_oe = oe3;
    assign y4 = a4; assign y4_oe = oe4;
endmodule

// Hex buffer: gates 1-4 on /G1, gates 5-6 on /G2. 367 = true, 368 = inverting
module cg_74x367 (input g1_n,g2_n,a1,a2,a3,a4,a5,a6,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe,y5,y5_oe,y6,y6_oe);
    assign {y1,y2,y3,y4,y5,y6} = {a1,a2,a3,a4,a5,a6};
    assign {y1_oe,y2_oe,y3_oe,y4_oe} = {4{~g1_n}};
    assign {y5_oe,y6_oe} = {2{~g2_n}};
endmodule

module cg_74x368 (input g1_n,g2_n,a1,a2,a3,a4,a5,a6,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe,y5,y5_oe,y6,y6_oe);
    assign {y1,y2,y3,y4,y5,y6} = ~{a1,a2,a3,a4,a5,a6};
    assign {y1_oe,y2_oe,y3_oe,y4_oe} = {4{~g1_n}};
    assign {y5_oe,y6_oe} = {2{~g2_n}};
endmodule

// Octal buffer, two groups of 4. 244 = true, 240 = inverting
module cg_74x244 (input oe1_n,oe2_n,
                  input a1_1,a1_2,a1_3,a1_4,a2_1,a2_2,a2_3,a2_4,
                  output y1_1,y1_1_oe,y1_2,y1_2_oe,y1_3,y1_3_oe,y1_4,y1_4_oe,
                  output y2_1,y2_1_oe,y2_2,y2_2_oe,y2_3,y2_3_oe,y2_4,y2_4_oe);
    assign {y1_1,y1_2,y1_3,y1_4} = {a1_1,a1_2,a1_3,a1_4};
    assign {y2_1,y2_2,y2_3,y2_4} = {a2_1,a2_2,a2_3,a2_4};
    assign {y1_1_oe,y1_2_oe,y1_3_oe,y1_4_oe} = {4{~oe1_n}};
    assign {y2_1_oe,y2_2_oe,y2_3_oe,y2_4_oe} = {4{~oe2_n}};
endmodule

module cg_74x240 (input oe1_n,oe2_n,
                  input a1_1,a1_2,a1_3,a1_4,a2_1,a2_2,a2_3,a2_4,
                  output y1_1,y1_1_oe,y1_2,y1_2_oe,y1_3,y1_3_oe,y1_4,y1_4_oe,
                  output y2_1,y2_1_oe,y2_2,y2_2_oe,y2_3,y2_3_oe,y2_4,y2_4_oe);
    assign {y1_1,y1_2,y1_3,y1_4} = ~{a1_1,a1_2,a1_3,a1_4};
    assign {y2_1,y2_2,y2_3,y2_4} = ~{a2_1,a2_2,a2_3,a2_4};
    assign {y1_1_oe,y1_2_oe,y1_3_oe,y1_4_oe} = {4{~oe1_n}};
    assign {y2_1_oe,y2_2_oe,y2_3_oe,y2_4_oe} = {4{~oe2_n}};
endmodule

// Octal buffer, enabled when both /OE1 and /OE2 are low. 541 true, 540 inv.
module cg_74x541 (input oe1_n,oe2_n,a1,a2,a3,a4,a5,a6,a7,a8,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe,
                  output y5,y5_oe,y6,y6_oe,y7,y7_oe,y8,y8_oe);
    wire en = ~oe1_n & ~oe2_n;
    assign {y1,y2,y3,y4,y5,y6,y7,y8} = {a1,a2,a3,a4,a5,a6,a7,a8};
    assign {y1_oe,y2_oe,y3_oe,y4_oe,y5_oe,y6_oe,y7_oe,y8_oe} = {8{en}};
endmodule

module cg_74x540 (input oe1_n,oe2_n,a1,a2,a3,a4,a5,a6,a7,a8,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe,
                  output y5,y5_oe,y6,y6_oe,y7,y7_oe,y8,y8_oe);
    wire en = ~oe1_n & ~oe2_n;
    assign {y1,y2,y3,y4,y5,y6,y7,y8} = ~{a1,a2,a3,a4,a5,a6,a7,a8};
    assign {y1_oe,y2_oe,y3_oe,y4_oe,y5_oe,y6_oe,y7_oe,y8_oe} = {8{en}};
endmodule

// Octal bus transceiver. DIR = 1: A -> B, DIR = 0: B -> A. /OE high = off.
module cg_74x245 (input dir, oe_n,
    input  a1_i,a2_i,a3_i,a4_i,a5_i,a6_i,a7_i,a8_i,
    output a1_o,a2_o,a3_o,a4_o,a5_o,a6_o,a7_o,a8_o,
    output a1_oe,a2_oe,a3_oe,a4_oe,a5_oe,a6_oe,a7_oe,a8_oe,
    input  b1_i,b2_i,b3_i,b4_i,b5_i,b6_i,b7_i,b8_i,
    output b1_o,b2_o,b3_o,b4_o,b5_o,b6_o,b7_o,b8_o,
    output b1_oe,b2_oe,b3_oe,b4_oe,b5_oe,b6_oe,b7_oe,b8_oe);
    assign {a1_o,a2_o,a3_o,a4_o,a5_o,a6_o,a7_o,a8_o} = {b1_i,b2_i,b3_i,b4_i,b5_i,b6_i,b7_i,b8_i};
    assign {b1_o,b2_o,b3_o,b4_o,b5_o,b6_o,b7_o,b8_o} = {a1_i,a2_i,a3_i,a4_i,a5_i,a6_i,a7_i,a8_i};
    assign {a1_oe,a2_oe,a3_oe,a4_oe,a5_oe,a6_oe,a7_oe,a8_oe} = {8{~oe_n & ~dir}};
    assign {b1_oe,b2_oe,b3_oe,b4_oe,b5_oe,b6_oe,b7_oe,b8_oe} = {8{~oe_n &  dir}};
endmodule

// ===========================================================================
// Decoders and multiplexers
// ===========================================================================

// 3-to-8 decoder, outputs active low
module cg_74x138 (input a,b,c,g1,g2a_n,g2b_n,
                  output y0,y1,y2,y3,y4,y5,y6,y7);
    wire en = g1 & ~g2a_n & ~g2b_n;
    wire [2:0] s = {c,b,a};
    assign {y7,y6,y5,y4,y3,y2,y1,y0} = en ? ~(8'b1 << s) : 8'hff;
endmodule

// Dual 2-to-4 decoder, outputs active low
module cg_74x139 (input g1_n,a1,b1,g2_n,a2,b2,
                  output y1_0,y1_1,y1_2,y1_3,y2_0,y2_1,y2_2,y2_3);
    assign {y1_3,y1_2,y1_1,y1_0} = g1_n ? 4'hf : ~(4'b1 << {b1,a1});
    assign {y2_3,y2_2,y2_1,y2_0} = g2_n ? 4'hf : ~(4'b1 << {b2,a2});
endmodule

// Dual 4-to-1 multiplexer, shared selects, active-low strobes
module cg_74x153 (input a,b,g1_n,c1_0,c1_1,c1_2,c1_3,g2_n,c2_0,c2_1,c2_2,c2_3,
                  output y1,y2);
    wire [1:0] s = {b,a};
    wire [3:0] c1 = {c1_3,c1_2,c1_1,c1_0};
    wire [3:0] c2 = {c2_3,c2_2,c2_1,c2_0};
    assign y1 = ~g1_n & c1[s];
    assign y2 = ~g2_n & c2[s];
endmodule

// Quad 2-to-1 multiplexer, S = 0 picks A, /G high forces outputs low
module cg_74x157 (input s,g_n,a1,b1,a2,b2,a3,b3,a4,b4, output y1,y2,y3,y4);
    assign y1 = ~g_n & (s ? b1 : a1);
    assign y2 = ~g_n & (s ? b2 : a2);
    assign y3 = ~g_n & (s ? b3 : a3);
    assign y4 = ~g_n & (s ? b4 : a4);
endmodule

// ===========================================================================
// Flip-flops and registers
// ===========================================================================

// Dual D flip-flop with async preset and clear (both low: Q = /Q = 1)
module cg_74x74 (input clr1_n,pre1_n,d1,clk1,clr2_n,pre2_n,d2,clk2,
                 output q1,q1_n,q2,q2_n);
    reg r1, r2;
    always @(posedge clk1 or negedge clr1_n or negedge pre1_n)
        if (!clr1_n) r1 <= 1'b0; else if (!pre1_n) r1 <= 1'b1; else r1 <= d1;
    always @(posedge clk2 or negedge clr2_n or negedge pre2_n)
        if (!clr2_n) r2 <= 1'b0; else if (!pre2_n) r2 <= 1'b1; else r2 <= d2;
    wire both1 = ~clr1_n & ~pre1_n;
    wire both2 = ~clr2_n & ~pre2_n;
    assign q1 = both1 | r1;  assign q1_n = both1 | ~r1;
    assign q2 = both2 | r2;  assign q2_n = both2 | ~r2;
endmodule

// Hex D flip-flop with async clear
module cg_74x174 (input clr_n,clk,d1,d2,d3,d4,d5,d6,
                  output q1,q2,q3,q4,q5,q6);
    reg [5:0] r;
    always @(posedge clk or negedge clr_n)
        if (!clr_n) r <= 6'b0; else r <= {d6,d5,d4,d3,d2,d1};
    assign {q6,q5,q4,q3,q2,q1} = r;
endmodule

// Quad D flip-flop with async clear and complementary outputs
module cg_74x175 (input clr_n,clk,d1,d2,d3,d4,
                  output q1,q1_n,q2,q2_n,q3,q3_n,q4,q4_n);
    reg [3:0] r;
    always @(posedge clk or negedge clr_n)
        if (!clr_n) r <= 4'b0; else r <= {d4,d3,d2,d1};
    assign {q4,q3,q2,q1} = r;
    assign {q4_n,q3_n,q2_n,q1_n} = ~r;
endmodule

// Octal D flip-flop with async clear
module cg_74x273 (input clr_n,clk,d1,d2,d3,d4,d5,d6,d7,d8,
                  output q1,q2,q3,q4,q5,q6,q7,q8);
    reg [7:0] r;
    always @(posedge clk or negedge clr_n)
        if (!clr_n) r <= 8'b0; else r <= {d8,d7,d6,d5,d4,d3,d2,d1};
    assign {q8,q7,q6,q5,q4,q3,q2,q1} = r;
endmodule

// Octal D flip-flop with clock enable (/E low = load)
module cg_74x377 (input e_n,clk,d1,d2,d3,d4,d5,d6,d7,d8,
                  output q1,q2,q3,q4,q5,q6,q7,q8);
    reg [7:0] r;
    always @(posedge clk)
        if (!e_n) r <= {d8,d7,d6,d5,d4,d3,d2,d1};
    assign {q8,q7,q6,q5,q4,q3,q2,q1} = r;
endmodule

// Octal transparent latch, 3-state (373 and 573 differ only in pinout)
module cg_74x373 (input oe_n,le,d1,d2,d3,d4,d5,d6,d7,d8,
                  output q1,q1_oe,q2,q2_oe,q3,q3_oe,q4,q4_oe,
                  output q5,q5_oe,q6,q6_oe,q7,q7_oe,q8,q8_oe);
    reg [7:0] l;
    always @* if (le) l = {d8,d7,d6,d5,d4,d3,d2,d1};
    assign {q8,q7,q6,q5,q4,q3,q2,q1} = l;
    assign {q1_oe,q2_oe,q3_oe,q4_oe,q5_oe,q6_oe,q7_oe,q8_oe} = {8{~oe_n}};
endmodule

// Octal D flip-flop, 3-state (374 and 574 differ only in pinout)
module cg_74x374 (input oe_n,clk,d1,d2,d3,d4,d5,d6,d7,d8,
                  output q1,q1_oe,q2,q2_oe,q3,q3_oe,q4,q4_oe,
                  output q5,q5_oe,q6,q6_oe,q7,q7_oe,q8,q8_oe);
    reg [7:0] r;
    always @(posedge clk) r <= {d8,d7,d6,d5,d4,d3,d2,d1};
    assign {q8,q7,q6,q5,q4,q3,q2,q1} = r;
    assign {q1_oe,q2_oe,q3_oe,q4_oe,q5_oe,q6_oe,q7_oe,q8_oe} = {8{~oe_n}};
endmodule

// ===========================================================================
// Counters
// ===========================================================================

// 4-bit synchronous binary counter. 161: async clear. 163: sync clear.
// /LOAD is synchronous. Counts when ENP & ENT. RCO = ENT & (Q == 15).
module cg_74x161 (input clr_n,clk,a,b,c,d,enp,ent,load_n,
                  output qa,qb,qc,qd,rco);
    reg [3:0] q;
    always @(posedge clk or negedge clr_n)
        if (!clr_n)       q <= 4'd0;
        else if (!load_n) q <= {d,c,b,a};
        else if (enp & ent) q <= q + 4'd1;
    assign {qd,qc,qb,qa} = q;
    assign rco = ent & (q == 4'hf);
endmodule

module cg_74x163 (input clr_n,clk,a,b,c,d,enp,ent,load_n,
                  output qa,qb,qc,qd,rco);
    reg [3:0] q;
    always @(posedge clk)
        if (!clr_n)       q <= 4'd0;
        else if (!load_n) q <= {d,c,b,a};
        else if (enp & ent) q <= q + 4'd1;
    assign {qd,qc,qb,qa} = q;
    assign rco = ent & (q == 4'hf);
endmodule

// ===========================================================================
// Shift registers
// ===========================================================================

// 8-bit serial-in parallel-out, serial data = A & B, async clear
module cg_74x164 (input a,b,clk,clr_n, output qa,qb,qc,qd,qe,qf,qg,qh);
    reg [7:0] r;
    always @(posedge clk or negedge clr_n)
        if (!clr_n) r <= 8'b0; else r <= {r[6:0], a & b};
    assign {qh,qg,qf,qe,qd,qc,qb,qa} = r;
endmodule

// 8-bit parallel-in serial-out. SH/LD low = async parallel load.
// Shifts A->H on the rising edge of (CLK | CLK INH).
module cg_74x165 (input sh_ld_n,clk,clk_inh,ser,a,b,c,d,e,f,g,h,
                  output qh,qh_n);
    reg  [7:0] r;
    wire [7:0] p  = {h,g,f,e,d,c,b,a};
    wire [8:0] ch = {r, ser};          // ch[i] feeds r[i]
    wire       ld = ~sh_ld_n;
    wire       ck = clk | clk_inh;
    genvar i;
    generate for (i = 0; i < 8; i = i + 1) begin : bit_
        wire s = ld &  p[i];
        wire c = ld & ~p[i];
        always @(posedge ck or posedge s or posedge c)
            if (c) r[i] <= 1'b0; else if (s) r[i] <= 1'b1; else r[i] <= ch[i];
    end endgenerate
    assign qh = r[7];
    assign qh_n = ~r[7];
endmodule

// 8-bit serial-in, parallel-out with output register, 3-state outputs.
// SRCLR is async (shift register only). QH' = serial out.
module cg_74x595 (input ser,srclk,srclr_n,rclk,oe_n,
                  output qa,qa_oe,qb,qb_oe,qc,qc_oe,qd,qd_oe,
                  output qe,qe_oe,qf,qf_oe,qg,qg_oe,qh,qh_oe,qh_s);
    reg [7:0] sr, out;
    always @(posedge srclk or negedge srclr_n)
        if (!srclr_n) sr <= 8'b0; else sr <= {sr[6:0], ser};
    always @(posedge rclk) out <= sr;
    assign {qh,qg,qf,qe,qd,qc,qb,qa} = out;
    assign {qa_oe,qb_oe,qc_oe,qd_oe,qe_oe,qf_oe,qg_oe,qh_oe} = {8{~oe_n}};
    assign qh_s = sr[7];
endmodule

// CD4021: 8-stage parallel-in serial-out. P/S high = async parallel load.
// Shifts on the rising clock edge: stage 1 <- SER, stage n <- stage n-1.
// Only stages 6, 7, 8 are brought out.
module cg_4021 (input ps,clk,ser,p1,p2,p3,p4,p5,p6,p7,p8, output q6,q7,q8);
    reg  [7:0] r;                      // r[0] = stage 1
    wire [7:0] p  = {p8,p7,p6,p5,p4,p3,p2,p1};
    wire [8:0] ch = {r, ser};
    genvar i;
    generate for (i = 0; i < 8; i = i + 1) begin : bit_
        wire s = ps &  p[i];
        wire c = ps & ~p[i];
        always @(posedge clk or posedge s or posedge c)
            if (c) r[i] <= 1'b0; else if (s) r[i] <= 1'b1; else r[i] <= ch[i];
    end endgenerate
    assign q6 = r[5];
    assign q7 = r[6];
    assign q8 = r[7];
endmodule

// ---------------------------------------------------------------------------
// More shift registers (pinouts and function tables checked against the
// TI / Harris datasheets: SN74HC594, SN74HC166, CD74HC597, CD74HC194,
// CD4094B, CD4015B, CD4014B).
// ---------------------------------------------------------------------------

// 74x594: 8-bit SIPO with output register; separate async clears (SRCLR for
// the shift register, RCLR for the output register); no output enable.
module cg_74x594 (input ser,srclk,srclr_n,rclk,rclr_n,
                  output qa,qb,qc,qd,qe,qf,qg,qh,qh_s);
    reg [7:0] sr, out;
    always @(posedge srclk or negedge srclr_n)
        if (!srclr_n) sr <= 8'b0; else sr <= {sr[6:0], ser};
    always @(posedge rclk or negedge rclr_n)
        if (!rclr_n) out <= 8'b0; else out <= sr;
    assign {qh,qg,qf,qe,qd,qc,qb,qa} = out;
    assign qh_s = sr[7];
endmodule

// 74x166: 8-bit PISO, synchronous parallel load (SH/LD low on the clock
// edge), async clear, clock inhibit (high = no clocking).
module cg_74x166 (input ser,clk,clk_inh,sh_ld_n,clr_n,a,b,c,d,e,f,g,h,
                  output qh);
    reg [7:0] r;
    wire ck = clk | clk_inh;
    always @(posedge ck or negedge clr_n)
        if (!clr_n) r <= 8'b0;
        else if (!sh_ld_n) r <= {h,g,f,e,d,c,b,a};
        else r <= {r[6:0], ser};
    assign qh = r[7];
endmodule

// 74x597: 8-bit input register (RCLK) feeding an 8-bit PISO shift register.
// SRLOAD low copies the input register into the shift register at once
// (async); SRCLR low clears it; SRCLK shifts while SRLOAD is high.
module cg_74x597 (input ser,srclk,srclr_n,rclk,srload_n,a,b,c,d,e,f,g,h,
                  output qh);
    reg [7:0] st, r;
    always @(posedge rclk) st <= {h,g,f,e,d,c,b,a};
    wire [8:0] ch = {r, ser};
    genvar i;
    generate for (i = 0; i < 8; i = i + 1) begin : bit_
        wire c = ~srclr_n | (~srload_n & ~st[i]);   // clear wins if both are low
        wire s = srclr_n & ~srload_n & st[i];
        always @(posedge srclk or posedge s or posedge c)
            if (c) r[i] <= 1'b0; else if (s) r[i] <= 1'b1; else r[i] <= ch[i];
    end endgenerate
    assign qh = r[7];
endmodule

// 74x194: 4-bit bidirectional universal shift register. S1 S0: 00 hold,
// 01 shift right (QA <- SR SER), 10 shift left (QD <- SL SER), 11 load.
module cg_74x194 (input clk,clr_n,s0,s1,sr_ser,sl_ser,a,b,c,d,
                  output qa,qb,qc,qd);
    reg [3:0] r;                       // r[0] = QA
    always @(posedge clk or negedge clr_n)
        if (!clr_n) r <= 4'b0;
        else case ({s1, s0})
            2'b01: r <= {r[2:0], sr_ser};
            2'b10: r <= {sl_ser, r[3:1]};
            2'b11: r <= {d, c, b, a};
            default: r <= r;
        endcase
    assign {qd,qc,qb,qa} = r;
endmodule

// CD4094 / 74x4094: 8-stage shift-and-store bus register. Shifts on the
// rising clock; the storage latches follow the shift register while STROBE
// is high; Q1..Q8 are 3-state (enabled by OUTPUT ENABLE high). QS is stage
// 8; Q'S is stage 8 again, taken on the falling clock edge (for cascading).
module cg_4094 (input data,clk,strobe,oe,
                output q1,q1_oe,q2,q2_oe,q3,q3_oe,q4,q4_oe,
                output q5,q5_oe,q6,q6_oe,q7,q7_oe,q8,q8_oe,qs,qs_d);
    reg [7:0] sr, st;
    reg       late;
    always @(posedge clk) sr <= {sr[6:0], data};
    always @* if (strobe) st = sr;
    always @(negedge clk) late <= sr[7];
    assign {q8,q7,q6,q5,q4,q3,q2,q1} = st;
    assign {q1_oe,q2_oe,q3_oe,q4_oe,q5_oe,q6_oe,q7_oe,q8_oe} = {8{oe}};
    assign qs = sr[7];
    assign qs_d = late;
endmodule

// CD4015: dual 4-stage SIPO; each half has its own clock, data and
// active-high async reset.
module cg_4015 (input clk_a,data_a,rst_a,clk_b,data_b,rst_b,
                output q1_a,q2_a,q3_a,q4_a,q1_b,q2_b,q3_b,q4_b);
    reg [3:0] ra, rb;
    always @(posedge clk_a or posedge rst_a)
        if (rst_a) ra <= 4'b0; else ra <= {ra[2:0], data_a};
    always @(posedge clk_b or posedge rst_b)
        if (rst_b) rb <= 4'b0; else rb <= {rb[2:0], data_b};
    assign {q4_a,q3_a,q2_a,q1_a} = ra;
    assign {q4_b,q3_b,q2_b,q1_b} = rb;
endmodule

// CD4014: as the CD4021 but the parallel load is synchronous: with P/S high
// the parallel inputs are loaded on the rising clock edge.
module cg_4014 (input ps,clk,ser,p1,p2,p3,p4,p5,p6,p7,p8, output q6,q7,q8);
    reg [7:0] r;                       // r[0] = stage 1
    always @(posedge clk)
        if (ps) r <= {p8,p7,p6,p5,p4,p3,p2,p1}; else r <= {r[6:0], ser};
    assign q6 = r[5];
    assign q7 = r[6];
    assign q8 = r[7];
endmodule


// ---- Single gates (74x1G..., SOT-23-5/6; pinouts from the TI SN74LVC1G datasheets)
module cg_1g00 (input a, b, output y);
    assign y = ~(a & b);
endmodule
module cg_1g02 (input a, b, output y);
    assign y = ~(a | b);
endmodule
module cg_1g08 (input a, b, output y);
    assign y = a & b;
endmodule
module cg_1g32 (input a, b, output y);
    assign y = a | b;
endmodule
module cg_1g86 (input a, b, output y);
    assign y = a ^ b;
endmodule
module cg_1g04 (input a, output y);
    assign y = ~a;
endmodule
module cg_1g07 (input a, output y);
    assign y = a;
endmodule
module cg_1g10 (input a, b, c, output y);
    assign y = ~(a & b & c);
endmodule
module cg_1g11 (input a, b, c, output y);
    assign y = a & b & c;
endmodule
module cg_1g27 (input a, b, c, output y);
    assign y = ~(a | b | c);
endmodule
module cg_1g125 (input oe_n, a, output y, y_oe);
    assign y = a;
    assign y_oe = ~oe_n;
endmodule
module cg_1g126 (input oe, a, output y, y_oe);
    assign y = a;
    assign y_oe = oe;
endmodule
module cg_1g240 (input oe_n, a, output y, y_oe);
    assign y = ~a;
    assign y_oe = ~oe_n;
endmodule
// Single D flip-flop, rising edge: '1G79 has Q, '1G80 has /Q
module cg_1g79 (input d, clk, output q);
    reg r;
    always @(posedge clk) r <= d;
    assign q = r;
endmodule
module cg_1g80 (input d, clk, output q_n);
    reg r;
    always @(posedge clk) r <= d;
    assign q_n = ~r;
endmodule


// ---- More glue (pinouts checked against the TI datasheets) --------------------
// Dual 4-input AND, triple 3-input NOR, 8-input NAND
module cg_74x21 (input a1,b1,c1,d1,a2,b2,c2,d2, output y1,y2);
    assign y1 = a1 & b1 & c1 & d1;
    assign y2 = a2 & b2 & c2 & d2;
endmodule

module cg_74x27 (input a1,b1,c1,a2,b2,c2,a3,b3,c3, output y1,y2,y3);
    assign y1 = ~(a1 | b1 | c1);
    assign y2 = ~(a2 | b2 | c2);
    assign y3 = ~(a3 | b3 | c3);
endmodule

module cg_74x30 (input a,b,c,d,e,f,g,h, output y);
    assign y = ~(a & b & c & d & e & f & g & h);
endmodule

// 8-to-1 multiplexer: Y and W = /Y; /G high forces Y low
module cg_74x151 (input d0,d1,d2,d3,d4,d5,d6,d7,a,b,c,g_n, output y,w);
    wire [7:0] dv = {d7,d6,d5,d4,d3,d2,d1,d0};
    assign y = ~g_n & dv[{c,b,a}];
    assign w = ~y;
endmodule

// 4-to-16 decoder, active-low outputs, enabled when /G1 and /G2 are low
module cg_74x154 (input a,b,c,d,g1_n,g2_n,
                  output y0,y1,y2,y3,y4,y5,y6,y7,y8,y9,y10,y11,y12,y13,y14,y15);
    wire en = ~g1_n & ~g2_n;
    wire [3:0] s = {d,c,b,a};
    wire [15:0] y = ~({15'b0, en} << s);
    assign {y15,y14,y13,y12,y11,y10,y9,y8,y7,y6,y5,y4,y3,y2,y1,y0} = y;
endmodule

// Quad 2-to-1 multiplexer, 3-state ('257 true, '258 inverted)
module cg_74x257 (input s,oe_n,a1,b1,a2,b2,a3,b3,a4,b4,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe);
    assign y1 = s ? b1 : a1;  assign y2 = s ? b2 : a2;
    assign y3 = s ? b3 : a3;  assign y4 = s ? b4 : a4;
    assign y1_oe = ~oe_n; assign y2_oe = ~oe_n; assign y3_oe = ~oe_n; assign y4_oe = ~oe_n;
endmodule

module cg_74x258 (input s,oe_n,a1,b1,a2,b2,a3,b3,a4,b4,
                  output y1,y1_oe,y2,y2_oe,y3,y3_oe,y4,y4_oe);
    assign y1 = ~(s ? b1 : a1);  assign y2 = ~(s ? b2 : a2);
    assign y3 = ~(s ? b3 : a3);  assign y4 = ~(s ? b4 : a4);
    assign y1_oe = ~oe_n; assign y2_oe = ~oe_n; assign y3_oe = ~oe_n; assign y4_oe = ~oe_n;
endmodule

// 8-bit addressable latch. /CLR low + /G high: clear; /CLR low + /G low:
// 1-of-8 demultiplexer; /CLR high + /G low: addressed latch follows D; both high: hold.
module cg_74x259 (input s0,s1,s2,d,g_n,clr_n, output q0,q1,q2,q3,q4,q5,q6,q7);
    reg [7:0] r;
    wire [2:0] sel = {s2,s1,s0};
    genvar i;
    generate for (i = 0; i < 8; i = i + 1) begin : bit_
        wire hit = ~g_n & (sel == i);
        always @* if (hit | ~clr_n) r[i] = hit & d;
    end endgenerate
    assign {q7,q6,q5,q4,q3,q2,q1,q0} = r;
endmodule

// 4-bit D register: loads when /G1 and /G2 are low, async clear (high),
// 3-state outputs enabled when M and N are low
module cg_74x173 (input m,n,g1_n,g2_n,clk,clr,d1,d2,d3,d4,
                  output q1,q1_oe,q2,q2_oe,q3,q3_oe,q4,q4_oe);
    reg [3:0] r;
    always @(posedge clk or posedge clr)
        if (clr) r <= 4'b0; else if (~g1_n & ~g2_n) r <= {d4,d3,d2,d1};
    assign {q4,q3,q2,q1} = r;
    wire oe = ~m & ~n;
    assign q1_oe = oe; assign q2_oe = oe; assign q3_oe = oe; assign q4_oe = oe;
endmodule

// 8-bit identity comparator ('688, '521): /P=Q low when P = Q and /G is low
module cg_74x688 (input g_n,p0,p1,p2,p3,p4,p5,p6,p7,q0,q1,q2,q3,q4,q5,q6,q7, output eq_n);
    assign eq_n = ~(~g_n & ({p7,p6,p5,p4,p3,p2,p1,p0} == {q7,q6,q5,q4,q3,q2,q1,q0}));
endmodule

// Dual J-/K flip-flop, rising edge, preset and clear ('109)
module cg_74x109 (input clr1_n,pre1_n,j1,k1_n,clk1,clr2_n,pre2_n,j2,k2_n,clk2,
                  output q1,q1_n,q2,q2_n);
    reg r1, r2;
    always @(posedge clk1 or negedge clr1_n or negedge pre1_n)
        if (!clr1_n) r1 <= 1'b0; else if (!pre1_n) r1 <= 1'b1;
        else r1 <= (j1 & ~r1) | (k1_n & r1);
    always @(posedge clk2 or negedge clr2_n or negedge pre2_n)
        if (!clr2_n) r2 <= 1'b0; else if (!pre2_n) r2 <= 1'b1;
        else r2 <= (j2 & ~r2) | (k2_n & r2);
    wire both1 = ~clr1_n & ~pre1_n;
    wire both2 = ~clr2_n & ~pre2_n;
    assign q1 = both1 | r1;  assign q1_n = both1 | ~r1;
    assign q2 = both2 | r2;  assign q2_n = both2 | ~r2;
endmodule

// Dual J-K flip-flop, falling edge, preset and clear ('112)
module cg_74x112 (input clr1_n,pre1_n,j1,k1,clk1,clr2_n,pre2_n,j2,k2,clk2,
                  output q1,q1_n,q2,q2_n);
    reg r1, r2;
    always @(negedge clk1 or negedge clr1_n or negedge pre1_n)
        if (!clr1_n) r1 <= 1'b0; else if (!pre1_n) r1 <= 1'b1;
        else r1 <= (j1 & ~r1) | (~k1 & r1);
    always @(negedge clk2 or negedge clr2_n or negedge pre2_n)
        if (!clr2_n) r2 <= 1'b0; else if (!pre2_n) r2 <= 1'b1;
        else r2 <= (j2 & ~r2) | (~k2 & r2);
    wire both1 = ~clr1_n & ~pre1_n;
    wire both2 = ~clr2_n & ~pre2_n;
    assign q1 = both1 | r1;  assign q1_n = both1 | ~r1;
    assign q2 = both2 | r2;  assign q2_n = both2 | ~r2;
endmodule

// 4-bit up/down counter, one clock ('191). D/U low = up. /LOAD is
// asynchronous. MAX/MIN: 15 counting up or 0 counting down. /RCO low while
// CLK is low, /CTEN low and MAX/MIN high.
module cg_74x191 (input a,b,c,d,load_n,cten_n,du,clk,
                  output qa,qb,qc,qd,maxmin,rco_n);
    reg  [3:0] r;
    wire [3:0] p = {d,c,b,a};
    wire [3:0] nxt = cten_n ? r : (du ? r - 4'd1 : r + 4'd1);
    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : bit_
        wire s = ~load_n &  p[i];
        wire cl = ~load_n & ~p[i];
        always @(posedge clk or posedge s or posedge cl)
            if (cl) r[i] <= 1'b0; else if (s) r[i] <= 1'b1; else r[i] <= nxt[i];
    end endgenerate
    assign {qd,qc,qb,qa} = r;
    assign maxmin = du ? (r == 4'd0) : (r == 4'd15);
    assign rco_n = ~(~clk & ~cten_n & maxmin);
endmodule

// 4-bit up/down counter, two clocks ('193): counts up on the rising edge of
// UP (DOWN high), down on the rising edge of DOWN (UP high). CLR (high) and
// /LOAD are asynchronous. A flip-flop notes which clock went low (on the
// falling edge of UP & DOWN), so the direction is settled before it rises.
module cg_74x193 (input a,b,c,d,load_n,clr,up,down,
                  output qa,qb,qc,qd,co_n,bo_n);
    reg  [3:0] r;
    reg        dir_up;
    wire ck = up & down;
    always @(negedge ck) dir_up <= ~up;
    wire [3:0] p = {d,c,b,a};
    wire [3:0] nxt = dir_up ? r + 4'd1 : r - 4'd1;
    genvar i;
    generate for (i = 0; i < 4; i = i + 1) begin : bit_
        wire s = ~clr & ~load_n & p[i];
        wire cl = clr | (~load_n & ~p[i]);
        always @(posedge ck or posedge s or posedge cl)
            if (cl) r[i] <= 1'b0; else if (s) r[i] <= 1'b1; else r[i] <= nxt[i];
    end endgenerate
    assign {qd,qc,qb,qa} = r;
    assign co_n = ~(~up & (r == 4'd15));
    assign bo_n = ~(~down & (r == 4'd0));
endmodule

// Dual 4-bit binary counter, falling edge, clear (high). Modelled as a
// synchronous counter: the real chip ripples, so its outputs settle in turn.
module cg_74x393 (input clk1,clr1,clk2,clr2,
                  output qa1,qb1,qc1,qd1,qa2,qb2,qc2,qd2);
    reg [3:0] r1, r2;
    always @(negedge clk1 or posedge clr1) if (clr1) r1 <= 4'b0; else r1 <= r1 + 4'd1;
    always @(negedge clk2 or posedge clr2) if (clr2) r2 <= 4'b0; else r2 <= r2 + 4'd1;
    assign {qd1,qc1,qb1,qa1} = r1;
    assign {qd2,qc2,qb2,qa2} = r2;
endmodule

// CD4040 12-stage binary counter, falling edge, reset (high)
module cg_4040 (input clk,rst, output q1,q2,q3,q4,q5,q6,q7,q8,q9,q10,q11,q12);
    reg [11:0] r;
    always @(negedge clk or posedge rst) if (rst) r <= 12'b0; else r <= r + 12'd1;
    assign {q12,q11,q10,q9,q8,q7,q6,q5,q4,q3,q2,q1} = r;
endmodule

// CD4017 decade counter (5-stage Johnson). Counts on the rising edge of CLK
// while CLOCK INHIBIT is low (or on INH falling while CLK is high).
module cg_4017 (input clk,inh,rst,
                output q0,q1,q2,q3,q4,q5,q6,q7,q8,q9,co);
    reg [4:0] j;
    wire ck = clk & ~inh;
    always @(posedge ck or posedge rst) if (rst) j <= 5'b0; else j <= {j[3:0], ~j[4]};
    assign q0 = ~j[0] & ~j[4];
    assign q1 =  j[0] & ~j[1];
    assign q2 =  j[1] & ~j[2];
    assign q3 =  j[2] & ~j[3];
    assign q4 =  j[3] & ~j[4];
    assign q5 =  j[4] &  j[0];
    assign q6 = ~j[0] &  j[1];
    assign q7 = ~j[1] &  j[2];
    assign q8 = ~j[2] &  j[3];
    assign q9 = ~j[3] &  j[4];
    assign co = ~j[4];
endmodule

// CD4013 dual D flip-flop, rising edge, set and reset (both active high;
// both high gives Q = /Q = 1)
module cg_4013 (input d1,clk1,set1,rst1,d2,clk2,set2,rst2, output q1,q1_n,q2,q2_n);
    reg r1, r2;
    always @(posedge clk1 or posedge rst1 or posedge set1)
        if (rst1) r1 <= 1'b0; else if (set1) r1 <= 1'b1; else r1 <= d1;
    always @(posedge clk2 or posedge rst2 or posedge set2)
        if (rst2) r2 <= 1'b0; else if (set2) r2 <= 1'b1; else r2 <= d2;
    wire both1 = set1 & rst1;
    wire both2 = set2 & rst2;
    assign q1 = both1 | r1;  assign q1_n = both1 | ~r1;
    assign q2 = both2 | r2;  assign q2_n = both2 | ~r2;
endmodule

// ---- Dual gates (74x2G..., TI SN74LVC2G pinouts) --------------------------------
module cg_2g00 (input a1,b1,a2,b2, output y1,y2);
    assign y1 = ~(a1 & b1);
    assign y2 = ~(a2 & b2);
endmodule
module cg_2g02 (input a1,b1,a2,b2, output y1,y2);
    assign y1 = ~(a1 | b1);
    assign y2 = ~(a2 | b2);
endmodule
module cg_2g08 (input a1,b1,a2,b2, output y1,y2);
    assign y1 = a1 & b1;
    assign y2 = a2 & b2;
endmodule
module cg_2g32 (input a1,b1,a2,b2, output y1,y2);
    assign y1 = a1 | b1;
    assign y2 = a2 | b2;
endmodule
module cg_2g86 (input a1,b1,a2,b2, output y1,y2);
    assign y1 = a1 ^ b1;
    assign y2 = a2 ^ b2;
endmodule
module cg_2g04 (input a1,a2, output y1,y2);
    assign y1 = ~a1;
    assign y2 = ~a2;
endmodule
module cg_2g07 (input a1,a2, output y1,y2);
    assign y1 = a1;
    assign y2 = a2;
endmodule
module cg_2g125 (input oe1_n,a1,oe2_n,a2, output y1,y1_oe,y2,y2_oe);
    assign y1 = a1;
    assign y1_oe = ~oe1_n;
    assign y2 = a2;
    assign y2_oe = ~oe2_n;
endmodule
module cg_2g126 (input oe1,a1,oe2,a2, output y1,y1_oe,y2,y2_oe);
    assign y1 = a1;
    assign y1_oe = oe1;
    assign y2 = a2;
    assign y2_oe = oe2;
endmodule
