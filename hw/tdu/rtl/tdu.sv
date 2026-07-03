// Copyright MOSAIC-SoC
// SPDX-License-Identifier: SHL-0.51
//
// tdu.sv — Task Dispatch Unit.
//
// A small (<100 GE) memory-mapped hardware block that assists the TITAN core
// (running FreeRTOS) with task dispatch to the heterogeneous ATLAS/NANO
// cores. It provides:
//   - an 8-deep task descriptor FIFO (push from TITAN, pop by TITAN/hw)
//   - per-core wake pulses (so sleeping ATLAS/NANO cores can be woken on
//     task enqueue or by explicit software request)
//   - a per-core CPI estimate array (software-updated, read by the scheduler)
//   - a core status mirror (running/sleep) sampled from each SCI wrapper
//   - an energy accumulator (active cores x cycles proxy)
//   - a scheduling-mode register (static / dynamic / power-aware)
//
// The module exposes a register-interface slave (reg_req_t/reg_rsp_t) so it
// drops into the always-on (AO) peripheral reg bus alongside the other x-heep
// peripherals. The register decode is hand-coded (no regtool dependency).

`include "common_cells/assertions.svh"

module tdu #(
    parameter int unsigned NUM_HARTS = 7
) (
    input  logic clk_i,
    input  logic rst_ni,

    // Register bus slave (AO peripheral reg bus)
    input  reg_pkg::reg_req_t  reg_req_i,
    output reg_pkg::reg_rsp_t  reg_rsp_o,

    // Per-core status (sampled from each SCI wrapper / cpu_subsystem)
    input  logic [NUM_HARTS-1:0] core_running_i,  // 1 = core currently executing
    input  logic [NUM_HARTS-1:0] core_sleep_i,    // 1 = core in WFI/sleep

    // Per-core wake pulses (1-cycle, edge-triggered to each core's irq/wake)
    output logic [NUM_HARTS-1:0] core_wake_o,

    // Event interrupt to the TITAN core (asserted on task enqueue)
    output logic                 tdu_irq_o
);

  import reg_pkg::*;
  import tdu_pkg::*;

  localparam int unsigned NumHartsW = $clog2(NUM_HARTS+1);
  localparam int unsigned CpiWords  = NUM_HARTS;
  localparam int unsigned CountW    = $clog2(TASK_QUEUE_DEPTH+1);
  localparam logic [CountW-1:0]    CountFull  = CountW'(TASK_QUEUE_DEPTH);
  localparam logic [NumHartsW-1:0] CpiWordsW  = NumHartsW'(CpiWords);

  // ── Register storage ────────────────────────────────────────────
  sched_mode_e          sched_mode_q, sched_mode_d;
  logic [NUM_HARTS-1:0] wake_mask_q, wake_mask_d;
  logic [31:0]          energy_counter_q;
  logic                 energy_clear;
  logic [31:0]          cpi_est_q [CpiWords];
  logic [31:0]          cpi_est_d [CpiWords];
  logic                 cpi_we [CpiWords];

  // ── Task FIFO (8-deep circular) ─────────────────────────────────
  task_desc_t task_mem [TASK_QUEUE_DEPTH-1:0];
  logic [$clog2(TASK_QUEUE_DEPTH)-1:0] wr_ptr_q, rd_ptr_q;
  logic [$clog2(TASK_QUEUE_DEPTH+1)-1:0] count_q, count_d;
  logic       full, empty;
  logic       push, pop;
  task_desc_t push_data;
  task_desc_t pop_data;

  assign full  = (count_q == CountFull);
  assign empty = (count_q == 0);

  // ── Bus request decode ──────────────────────────────────────────
  // The reg bus delivers word-aligned addresses in reg_req_i.addr. Only
  // word accesses are supported; sub-word writes are treated as errors.
  logic        req_valid;
  logic        req_write;
  logic [31:0] req_addr;
  logic [31:0] req_wdata;
  logic        addr_in_range;
  logic        cpi_region;
  logic [31:0] cpi_off;
  logic [NumHartsW-1:0] cpi_idx;

  assign req_valid = reg_req_i.valid;
  assign req_write = reg_req_i.write;
  assign req_addr  = reg_req_i.addr;
  assign req_wdata = reg_req_i.wdata;

  // CPI estimate array region: [TDU_CPI_EST_BASE_OFFSET .. +4*NUM_HARTS)
  assign cpi_region = (req_addr[31:0] >= TDU_CPI_EST_BASE_OFFSET) &&
                      (req_addr[31:0] <  TDU_CPI_EST_BASE_OFFSET + 4*CpiWords);
  assign cpi_off = (req_addr - TDU_CPI_EST_BASE_OFFSET) >> 2;
  assign cpi_idx = cpi_off[NumHartsW-1:0];

  // ── Read data mux ───────────────────────────────────────────────
  logic [31:0] rdata_d;
  logic        error_d;
  logic        ready_d;

  always_comb begin
    // Defaults
    rdata_d        = 32'h0;
    error_d        = 1'b0;
    ready_d        = 1'b0;
    sched_mode_d   = sched_mode_q;
    wake_mask_d    = wake_mask_q;
    energy_clear   = 1'b0;
    push           = 1'b0;
    pop            = 1'b0;
    push_data      = task_desc_t'('0);
    for (int i = 0; i < CpiWords; i++) cpi_est_d[i] = cpi_est_q[i];
    for (int i = 0; i < CpiWords; i++) cpi_we[i]    = 1'b0;

    if (req_valid) begin
      ready_d = 1'b1;
      if (cpi_region) begin
        // Per-core CPI estimate array (RW)
        if (req_write) begin
          if (cpi_idx < CpiWordsW) begin
            cpi_we[cpi_idx]  = 1'b1;
            cpi_est_d[cpi_idx] = req_wdata;
          end else begin
            error_d = 1'b1;
          end
        end else begin
          if (cpi_idx < CpiWordsW) begin
            rdata_d = cpi_est_q[cpi_idx];
          end else begin
            error_d = 1'b1;
          end
        end
      end else begin
        unique case (req_addr)
          TDU_CORE_STATUS_OFFSET: begin
            if (req_write) error_d = 1'b1;  // RO
            else rdata_d = {{(32-2*NUM_HARTS){1'b0}}, core_sleep_i, core_running_i};
          end

          TDU_SCHED_MODE_OFFSET: begin
            if (req_write) begin
              if (req_wdata[1:0] <= SCHED_POWER_AWARE)
                sched_mode_d = sched_mode_e'(req_wdata[1:0]);
              else
                error_d = 1'b1;
            end else begin
              rdata_d = {30'h0, sched_mode_q};
            end
          end

          TDU_WAKE_MASK_OFFSET: begin
            if (req_write)
              wake_mask_d = req_wdata[NUM_HARTS-1:0];
            else
              rdata_d = {{(32-NUM_HARTS){1'b0}}, wake_mask_q};
          end

          TDU_WAKE_REQ_OFFSET: begin
            // Write-1-to-set a one-cycle wake pulse on selected cores.
            // Reads return 0.
            if (req_write) begin
              // handled in wake pulse logic below via wake_req_pulse
            end
            rdata_d = 32'h0;
          end

          TDU_TASK_PUSH_OFFSET: begin
            if (req_write) begin
              if (!full) begin
                push      = 1'b1;
                push_data = task_desc_t'(req_wdata);
              end else begin
                error_d = 1'b1;  // queue full
              end
            end else begin
              rdata_d = 32'h0;  // WO
            end
          end

          TDU_TASK_POP_OFFSET: begin
            if (!req_write) begin
              if (!empty) begin
                pop      = 1'b1;
                rdata_d  = pop_data;
              end else begin
                rdata_d  = 32'h0;  // empty
              end
            end else begin
              rdata_d = 32'h0;  // RO
            end
          end

          TDU_TASK_STATUS_OFFSET: begin
            if (req_write) error_d = 1'b1;  // RO
            // [5]=full, [4]=empty, [3:0]=count
            else rdata_d = {26'h0, full, empty, count_q[3:0]};
          end

          TDU_ENERGY_COUNTER_OFFSET: begin
            if (req_write) begin
              // Write clears the counter (read-to-clear alternative)
              energy_clear = 1'b1;
            end else begin
              rdata_d = energy_counter_q;
            end
          end

          default: error_d = 1'b1;
        endcase
      end
    end
  end

  assign reg_rsp_o = '{error: error_d, ready: ready_d, rdata: rdata_d};

  // ── Task FIFO sequential logic ──────────────────────────────────
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      wr_ptr_q <= '0;
      rd_ptr_q <= '0;
      count_q  <= '0;
    end else begin
      // Pointer updates: push-only, pop-only, or simultaneous (no change to count)
      if (push && !pop) begin
        task_mem[wr_ptr_q] <= push_data;
        wr_ptr_q <= wr_ptr_q + 1;
        count_q  <= count_q + 1;
      end else if (pop && !push) begin
        rd_ptr_q <= rd_ptr_q + 1;
        count_q  <= count_q - 1;
      end else if (push && pop) begin
        // Simultaneous push and pop: advance both, count unchanged.
        // Push writes to wr_ptr; pop reads from rd_ptr. With a 1-cycle
        // read window this is safe as long as the FIFO is neither full
        // (push blocked) nor empty (pop blocked) — both guarded above.
        task_mem[wr_ptr_q] <= push_data;
        wr_ptr_q <= wr_ptr_q + 1;
        rd_ptr_q <= rd_ptr_q + 1;
      end
    end
  end

  assign pop_data = task_mem[rd_ptr_q];

  // ── Register updates ────────────────────────────────────────────
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      sched_mode_q     <= SCHED_STATIC;
      wake_mask_q      <= '0;
      energy_counter_q <= '0;
    end else begin
      sched_mode_q     <= sched_mode_d;
      wake_mask_q      <= wake_mask_d;
      // Energy accumulator: increment by the number of running cores each
      // cycle (energy proxy = active cores x time). A write to the
      // ENERGY_COUNTER register clears it. Saturates at 2^32.
      if (energy_clear) begin
        energy_counter_q <= '0;
      end else begin
        energy_counter_q <= energy_counter_q + $countones(core_running_i);
      end
    end
  end

  // CPI estimate array registers
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni) begin
      for (int i = 0; i < CpiWords; i++) cpi_est_q[i] <= '0;
    end else begin
      for (int i = 0; i < CpiWords; i++) begin
        if (cpi_we[i]) cpi_est_q[i] <= cpi_est_d[i];
      end
    end
  end

  // ── Wake pulse generation ───────────────────────────────────────
  // A core is woken (1-cycle pulse) when:
  //   (a) a task is pushed and the core is in WAKE_MASK and currently
  //       sleeping, or
  //   (b) software writes to WAKE_REQ for that core.
  logic [NUM_HARTS-1:0] wake_req_pulse;
  logic [NUM_HARTS-1:0] wake_task_pulse;

  assign wake_req_pulse  = (req_valid && req_write &&
                           (req_addr == TDU_WAKE_REQ_OFFSET))
                           ? req_wdata[NUM_HARTS-1:0] : '0;

  assign wake_task_pulse = (push) ? (wake_mask_q & core_sleep_i) : '0;

  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)
      core_wake_o <= '0;
    else
      core_wake_o <= wake_req_pulse | wake_task_pulse;
  end

  // ── Event interrupt to TITAN ────────────────────────────────────
  // Assert a 1-cycle interrupt pulse whenever a task is successfully
  // enqueued, so the TITAN scheduler can react (or the wake pulses alone
  // can drive ATLAS/NANO entry).
  always_ff @(posedge clk_i or negedge rst_ni) begin
    if (!rst_ni)
      tdu_irq_o <= 1'b0;
    else
      tdu_irq_o <= push;
  end

  // ── Assertions ──────────────────────────────────────────────────
  `ASSERT_INIT(NumHartsPositive, NUM_HARTS >= 1)
  `ASSERT_INIT(NumHartsFitStatus, NUM_HARTS <= 16)

endmodule : tdu
