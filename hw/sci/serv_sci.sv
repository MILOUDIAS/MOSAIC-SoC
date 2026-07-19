// Copyright MOSAIC-SoC
// SPDX-License-Identifier: SHL-0.51
//
// serv_sci.sv — Standard Core Interface wrapper for SERV (via servile).
//
// Wraps SERV+servile, converting its unified Wishbone Lite master port
// (I+D arbitrated by servile internally) to OBI v1.3.
//
// servile port map (from refs/IP_Cores_Catalog/serv/servile/servile.v):
//   i_clk, i_rst (active-high), i_timer_irq
//   o_wb_mem_adr/dat/sel/we/stb, i_wb_mem_rdt/ack  (unified I+D bus)
//   o_wb_ext_adr/dat/sel/we/stb, i_wb_ext_rdt/ack  (extension bus)
//   o_rf_waddr/wdata/wen, o_rf_raddr, i_rf_rdata, o_rf_ren  (register file)
//
// SERV has no hart_id port, no debug interface, no fetch_enable (starts at
// reset_pc), and no WFI/sleep output. The register file is provided by
// serv_rf_ram (a simple dual-port RAM).

module serv_sci #(
    parameter int unsigned W = 1,               // 1=SERV, 4=QERV
    parameter bit WITH_CSR = 1'b1,
    parameter bit COMPRESSED = 1'b0,
    parameter bit MDU = 1'b0,
    parameter bit PRE_REGISTER = 1'b0,
    parameter logic [31:0] RESET_PC = 32'h00000180
) (
    input logic clk_i,
    input logic rst_ni,

    // Core control
    input  logic [31:0] hart_id_i,    // unused — SERV has no mhartid
    // fetch_enable_i: SERV has no native fetch-enable, so we emulate a dormant
    // worker by holding the core in reset until this is asserted (driven by the
    // per-hart wake latch in cpu_subsystem → TDU.core_wake_o). Closes the loop.
    input  logic        fetch_enable_i,
    output logic        core_sleep_o,

    // Interrupts
    input  logic [31:0] irq_i,

    // Debug
    input  logic        debug_req_i,  // unused — SERV has no debug port

    // OBI unified master port (read-write, arbitrated I+D)
    output obi_pkg::obi_req_t  mem_req_o,
    input  obi_pkg::obi_resp_t mem_resp_i
);

    // ── servile Wishbone Lite signals ────────────────────────────
    logic [31:0] wb_adr;
    logic [31:0] wb_dat_o;   // write data from core
    logic [31:0] wb_dat_i;   // read data to core
    logic [3:0]  wb_sel;
    logic        wb_we;
    logic        wb_stb;
    logic        wb_ack;

    // ── servile RF signals ────────────────────────────────────────
    localparam int unsigned RfWidth = W * 2;
    localparam int unsigned RfRegs  = 32 + (WITH_CSR ? 4 : 0);
    localparam int unsigned RfDepth = RfRegs * 32 / RfWidth;
    localparam int unsigned RfL2d   = $clog2(RfDepth);

    logic [RfL2d-1:0]   rf_waddr;
    logic [RfWidth-1:0] rf_wdata;
    logic               rf_wen;
    logic [RfL2d-1:0]   rf_raddr;
    logic               rf_ren;
    logic [RfWidth-1:0] rf_rdata;

    // ── Register file (serv_rf_ram) ──────────────────────────────
    serv_rf_ram #(
        .width  (RfWidth),
        .csr_regs(WITH_CSR ? 4 : 0)
    ) rf_ram_i (
        .i_clk   (clk_i),
        .i_waddr (rf_waddr),
        .i_wdata (rf_wdata),
        .i_wen   (rf_wen),
        .i_raddr (rf_raddr),
        .i_ren   (rf_ren),
        .o_rdata (rf_rdata)
    );

    // ── servile instantiation ────────────────────────────────────
    servile #(
        .width     (W),
        .reset_pc  (RESET_PC),
        .with_c    (COMPRESSED),
        .with_csr  (WITH_CSR),
        .with_mdu  (MDU),
        .pre_register(PRE_REGISTER)
    ) i_servile (
        .i_clk       (clk_i),
        // Active-high reset. Held asserted while the system is in reset OR the
        // core has not yet been woken (fetch_enable_i low) → dormant worker.
        .i_rst       (~rst_ni | ~fetch_enable_i),

        // SERV only has a timer IRQ (no external/software in standard mode)
        .i_timer_irq (irq_i[7]),

        // Wishbone Lite memory bus (unified I+D via internal arbiter)
        .o_wb_mem_adr(wb_adr),
        .o_wb_mem_dat(wb_dat_o),
        .o_wb_mem_sel(wb_sel),
        .o_wb_mem_we (wb_we),
        .o_wb_mem_stb(wb_stb),
        .i_wb_mem_rdt(wb_dat_i),
        .i_wb_mem_ack(wb_ack),

        // Extension bus (unused — tie off)
        .o_wb_ext_adr(),
        .o_wb_ext_dat(),
        .o_wb_ext_sel(),
        .o_wb_ext_we (),
        .o_wb_ext_stb(),
        .i_wb_ext_rdt('0),
        .i_wb_ext_ack(1'b0),

        // Register file interface
        .o_rf_waddr  (rf_waddr),
        .o_rf_wdata  (rf_wdata),
        .o_rf_wen    (rf_wen),
        .o_rf_raddr  (rf_raddr),
        .i_rf_rdata  (rf_rdata),
        .o_rf_ren    (rf_ren)
    );

    // ── Wishbone Lite → OBI conversion (single outstanding) ─────────────
    // OBI separates acceptance (gnt) from response (rvalid). Against the real
    // system xbar gnt asserts when the request is accepted and rvalid the NEXT
    // cycle (or later under contention), so the previous "ack = gnt & rvalid"
    // almost never fired (the two rarely coincide) and SERV stalled. Track one
    // outstanding transaction — drop req once accepted (gnt) until its response
    // (rvalid) returns — and ack the Wishbone bus on rvalid (= data valid).
    // servile registers its read data on ack, so no read-data hold is needed.
    // Against a 0-latency memory (gnt+rvalid same cycle, tb/mosaic) this still
    // completes in one cycle.
    logic mem_outstanding_q;
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni)                              mem_outstanding_q <= 1'b0;
      else if (mem_resp_i.rvalid)               mem_outstanding_q <= 1'b0;
      else if (mem_req_o.req && mem_resp_i.gnt) mem_outstanding_q <= 1'b1;
    end

    // Gate with fetch_enable_i so a dormant worker stays bus-silent (SERV is
    // held in reset while parked, but mask the strobe too for defense in depth).
    assign mem_req_o.req       = wb_stb & fetch_enable_i & ~mem_outstanding_q;
    assign mem_req_o.addr      = wb_adr;
    assign mem_req_o.we        = wb_we;
    assign mem_req_o.be        = wb_sel;
    assign mem_req_o.wdata     = wb_dat_o;

    assign wb_ack              = mem_resp_i.rvalid;
    assign wb_dat_i            = mem_resp_i.rdata;

    // SERV has no native WFI/sleep output. Report "asleep" while the core is
    // held dormant (not yet woken) so the TDU's CORE_STATUS reflects which
    // workers are still parked — drives the wake-scheduling loop.
    assign core_sleep_o        = ~fetch_enable_i;

endmodule : serv_sci
