// Copyright MOSAIC-SoC
// SPDX-License-Identifier: SHL-0.51
//
// tdu_tb.sv — Self-checking testbench for the Task Dispatch Unit.
// Verifies: register read/write, task FIFO push/pop ordering and status,
// wake-pulse generation, CPI estimate array, energy counter, error paths.

`timescale 1ns/1ps

module tdu_tb;

  localparam int unsigned NUM_HARTS = 7;
  localparam time CLK_PERIOD = 10ns;

  logic clk;
  logic rst_n;

  reg_pkg::reg_req_t req;
  reg_pkg::reg_rsp_t rsp;

  logic [NUM_HARTS-1:0] core_running;
  logic [NUM_HARTS-1:0] core_sleep;
  logic [NUM_HARTS-1:0] core_wake;
  logic                 tdu_irq;

  int errors = 0;

  // ── DUT ─────────────────────────────────────────────────────────
  tdu #(
      .NUM_HARTS(NUM_HARTS)
  ) dut (
      .clk_i          (clk),
      .rst_ni         (rst_n),
      .reg_req_i      (req),
      .reg_rsp_o      (rsp),
      .core_running_i (core_running),
      .core_sleep_i   (core_sleep),
      .core_wake_o    (core_wake),
      .tdu_irq_o      (tdu_irq)
  );

  // ── Clock ───────────────────────────────────────────────────────
  initial clk = 1'b0;
  always #(CLK_PERIOD/2) clk = ~clk;

  // ── Bus transaction tasks (drive on negedge to avoid races) ─────
  task automatic bus_write(input logic [31:0] addr, input logic [31:0] data);
    @(negedge clk);
    req.valid = 1'b1;
    req.write = 1'b1;
    req.addr  = addr;
    req.wdata = data;
    req.wstrb = 4'hF;
    do @(posedge clk); while (!rsp.ready);
    @(negedge clk);
    req.valid = 1'b0;
    req.write = 1'b0;
    req.wstrb = 4'h0;
  endtask

  task automatic bus_read(input logic [31:0] addr, output logic [31:0] data);
    @(negedge clk);
    req.valid = 1'b1;
    req.write = 1'b0;
    req.addr  = addr;
    req.wdata = 32'h0;
    req.wstrb = 4'hF;
    do @(posedge clk); while (!rsp.ready);
    data = rsp.rdata;
    @(negedge clk);
    req.valid = 1'b0;
    req.wstrb = 4'h0;
  endtask

  task automatic check(input logic [31:0] got, input logic [31:0] exp, input string msg);
    if (got !== exp) begin
      $display("[FAIL] %s: got 0x%08h, expected 0x%08h", msg, got, exp);
      errors++;
    end else begin
      $display("[PASS] %s: 0x%08h", msg, got);
    end
  endtask

  logic [31:0] rdata;

  // ── Stimulus ────────────────────────────────────────────────────
  initial begin
    req.valid    = 1'b0;
    req.write    = 1'b0;
    req.addr     = 32'h0;
    req.wdata    = 32'h0;
    req.wstrb    = 4'h0;
    core_running = '0;
    core_sleep   = '0;
    rst_n        = 1'b0;
    repeat (4) @(posedge clk);
    @(negedge clk);
    rst_n = 1'b1;
    repeat (2) @(posedge clk);

    // ── 1. Default SCHED_MODE is STATIC (0) ──
    bus_read(32'h04, rdata);
    check(rdata, 32'h0, "default SCHED_MODE");

    // ── 2. Write SCHED_MODE = DYNAMIC ──
    bus_write(32'h04, 32'h1);
    bus_read(32'h04, rdata);
    check(rdata, 32'h1, "SCHED_MODE=DYNAMIC");

    // ── 3. Write WAKE_MASK = cores 1..6 ──
    bus_write(32'h08, 32'h7E);
    bus_read(32'h08, rdata);
    check(rdata, 32'h7E, "WAKE_MASK");

    // ── 4. Task FIFO empty at reset: [4]=empty -> 0x10 ──
    bus_read(32'h18, rdata);
    check(rdata, 32'h10, "TASK_STATUS empty");

    // ── 5. Push 3 tasks (distinctive values; FIFO is transparent) ──
    bus_write(32'h10, 32'hAAAA0001);
    bus_write(32'h10, 32'hBBBB0002);
    bus_write(32'h10, 32'hCCCC0003);

    bus_read(32'h18, rdata);  // count=3, not empty/full -> 0x03
    check(rdata, 32'h03, "TASK_STATUS count=3");

    // ── 6. Pop tasks (FIFO order: A, B, C) ──
    bus_read(32'h14, rdata);
    check(rdata, 32'hAAAA0001, "POP task A");
    bus_read(32'h14, rdata);
    check(rdata, 32'hBBBB0002, "POP task B");
    bus_read(32'h14, rdata);
    check(rdata, 32'hCCCC0003, "POP task C");

    bus_read(32'h18, rdata);
    check(rdata, 32'h10, "TASK_STATUS empty again");

    // ── 7. Wake pulse on task push (core 1 sleeping, in mask 0x7E) ──
    core_sleep = 7'b0000010;  // core 1 sleeping
    @(negedge clk);
    req.valid = 1'b1; req.write = 1'b1; req.addr = 32'h10; req.wdata = 32'hDDDD0004; req.wstrb = 4'hF;
    @(posedge clk);  // push accepted, wake pulse registered next cycle
    @(posedge clk);
    if (core_wake[1] !== 1'b1) begin
      $display("[FAIL] wake pulse on push for core 1: got %b", core_wake);
      errors++;
    end else $display("[PASS] wake pulse on push for core 1");
    @(negedge clk);
    req.valid = 1'b0; req.write = 1'b0; req.wstrb = 4'h0;
    core_sleep = '0;
    // drain the pushed task
    bus_read(32'h14, rdata);

    // ── 8. WAKE_REQ manual wake (write 1<<5) ──
    @(negedge clk);
    req.valid = 1'b1; req.write = 1'b1; req.addr = 32'h0C; req.wdata = 32'h20; req.wstrb = 4'hF;
    @(posedge clk);
    @(posedge clk);
    if (core_wake[5] !== 1'b1) begin
      $display("[FAIL] manual WAKE_REQ core 5: got %b", core_wake);
      errors++;
    end else $display("[PASS] manual WAKE_REQ core 5");
    @(negedge clk);
    req.valid = 1'b0; req.write = 1'b0; req.wstrb = 4'h0;

    // ── 9. CORE_STATUS: running=0x01 (bit0), sleep=0x02 (bit8 of field) ──
    // Layout: {sleep[13:7], running[6:0]}. running=1 -> bit0; sleep=2 -> bit8.
    core_running = 7'b0000001;
    core_sleep   = 7'b0000010;
    @(negedge clk);
    bus_read(32'h00, rdata);
    check(rdata, 32'h0000_0101, "CORE_STATUS");
    core_running = '0;
    core_sleep   = '0;

    // ── 10. CPI estimate array ──
    bus_write(32'h20 + 4*2, 32'h0000_0007);  // core 2 CPI = 7
    bus_read(32'h20 + 4*2, rdata);
    check(rdata, 32'h0000_0007, "CPI_EST[2]");
    bus_read(32'h20 + 4*0, rdata);
    check(rdata, 32'h0, "CPI_EST[0] default");

    // ── 11. Energy counter increments with running cores ──
    bus_write(32'h1C, 32'h0);  // clear
    bus_read(32'h1C, rdata);
    check(rdata, 32'h0, "ENERGY cleared");
    core_running = 7'b0000011;  // 2 cores running
    repeat (5) @(posedge clk);
    @(negedge clk);
    core_running = '0;
    bus_read(32'h1C, rdata);
    if (rdata == 32'h0) begin
      $display("[FAIL] ENERGY did not increment: 0x%08h", rdata);
      errors++;
    end else $display("[PASS] ENERGY incremented to 0x%08h", rdata);

    // ── 12. Read-only path: write to CORE_STATUS is ignored ──
    bus_write(32'h00, 32'hDEAD);
    bus_read(32'h00, rdata);
    check(rdata, 32'h0, "CORE_STATUS RO (write ignored)");

    // ── Summary ───────────────────────────────────────────────────
    repeat (4) @(posedge clk);
    if (errors == 0)
      $display("\n=== TDU TB: ALL TESTS PASSED ===");
    else
      $display("\n=== TDU TB: %0d FAILURES ===", errors);
    $finish;
  end

  // Watchdog
  initial begin
    #(20000ns);
    $display("[FAIL] Watchdog timeout");
    $finish;
  end

endmodule
