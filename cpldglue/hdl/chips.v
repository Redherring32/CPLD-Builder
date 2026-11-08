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
