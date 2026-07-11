// Copyright 2022 OpenHW Group
// Solderpad Hardware License, Version 2.1, see LICENSE.md for details.
// SPDX-License-Identifier: Apache-2.0 WITH SHL-2.1

<%!
  # Helper: build SV param list for a CPU instantiation
  def _cv32e20_params(cpu, xif):
      p = []
      if cpu.is_defined("rv32e"):
          p.append(f".RV32E({cpu.get_sv_str('rv32e')})")
      if cpu.is_defined("rv32m"):
          p.append(f".RV32M(cve2_pkg::{cpu.get_sv_str('rv32m')})")
      if xif is not None:
          p.append(f".X_INTERFACE(1'b1)")
          p.append(f".X_INTERFACE_NUM_RS({xif.x_num_rs})")
      if cpu.is_defined("num_mhpmcounters"):
          p.append(f".MHPMCounterNum({cpu.get_sv_str('num_mhpmcounters')})")
      return p

  def _cv32e40x_params(cpu, xif):
      p = []
      if xif is not None:
          p.append(f".X_INTERFACE(1'b1)")
          p.append(f".X_NUM_RS({xif.x_num_rs})")
          p.append(f".X_ID_WIDTH({xif.x_id_width})")
          p.append(f".X_MEM_WIDTH({xif.x_mem_width})")
          p.append(f".X_RFR_WIDTH({xif.x_rfr_width})")
          p.append(f".X_RFW_WIDTH({xif.x_rfw_width})")
          p.append(f".X_MISA({xif.x_misa})")
          p.append(f".X_ECS_XS({xif.x_ecs_xs})")
      if cpu.is_defined("num_mhpmcounters"):
          p.append(f".NUM_MHPMCOUNTERS({cpu.get_sv_str('num_mhpmcounters')})")
      p.append(f".DBG_NUM_TRIGGERS(0)")
      return p

  def _cv32e40px_params(cpu, xif):
      p = []
      if cpu.is_defined("fpu"):
          p.append(f".FPU({cpu.get_sv_str('fpu')})")
      if cpu.is_defined("fpu_addmul_lat"):
          p.append(f".FPU_ADDMUL_LAT({cpu.get_sv_str('fpu_addmul_lat')})")
      if cpu.is_defined("fpu_others_lat"):
          p.append(f".FPU_OTHERS_LAT({cpu.get_sv_str('fpu_others_lat')})")
      if cpu.is_defined("zfinx"):
          p.append(f".ZFINX({cpu.get_sv_str('zfinx')})")
      if cpu.is_defined("corev_pulp"):
          p.append(f".COREV_PULP({cpu.get_sv_str('corev_pulp')})")
      if cpu.is_defined("num_mhpmcounters"):
          p.append(f".NUM_MHPMCOUNTERS({cpu.get_sv_str('num_mhpmcounters')})")
      if xif is not None:
          p.append(f".X_INTERFACE(1'b1)")
          p.append(f".X_INTERFACE_NUM_RS({xif.x_num_rs})")
      return p

  def _cv32e40p_params(cpu, xif):
      p = []
      if cpu.is_defined("fpu"):
          p.append(f".FPU({cpu.get_sv_str('fpu')})")
      if cpu.is_defined("fpu_addmul_lat"):
          p.append(f".FPU_ADDMUL_LAT({cpu.get_sv_str('fpu_addmul_lat')})")
      if cpu.is_defined("fpu_others_lat"):
          p.append(f".FPU_OTHERS_LAT({cpu.get_sv_str('fpu_others_lat')})")
      if cpu.is_defined("zfinx"):
          p.append(f".ZFINX({cpu.get_sv_str('zfinx')})")
      if cpu.is_defined("corev_pulp"):
          p.append(f".COREV_PULP({cpu.get_sv_str('corev_pulp')})")
      if cpu.is_defined("num_mhpmcounters"):
          p.append(f".NUM_MHPMCOUNTERS({cpu.get_sv_str('num_mhpmcounters')})")
      return p
%>

<%
  cpu = xheep.cpu()
  xif = xheep.xif()
  is_mc = xheep.is_multi_core()
  cpus = xheep.cpus()
  nh = xheep.num_harts()
%>

% if is_mc:

// ─── Multi-core cpu_subsystem ──────────────────────────────────────
module cpu_subsystem
  import obi_pkg::*;
  import core_v_mini_mcu_pkg::*;
#(
    parameter int NUM_HARTS = ${nh},
    parameter BOOT_ADDR = 'h180,
    parameter DM_HALTADDRESS = '0
) (
    // Clock and Reset
    input logic clk_i,
    input logic rst_ni,

    // Per-hart array ports use a DESCENDING [NUM_HARTS-1:0] range to match the
    // top's intermediates and system_bus ports (also [NRHARTS-1:0]). A range
    // mismatch ([NUM_HARTS] ascending here vs [N-1:0] descending there) reverses
    // the unpacked-array element mapping on connection (element-by-position), so
    // e.g. core 0's traffic/hart_id/irq would land on array index N-1. (NH=1 can't
    // expose this — which is why the single-core sim passed.)

    // Core IDs (one per hart)
    input  logic [31:0] hart_id_i [NUM_HARTS-1:0],

    // Instruction memory interfaces (one per hart)
    output obi_req_t  core_instr_req_o [NUM_HARTS-1:0],
    input  obi_resp_t core_instr_resp_i [NUM_HARTS-1:0],

    // Data memory interfaces (one per hart)
    output obi_req_t  core_data_req_o [NUM_HARTS-1:0],
    input  obi_resp_t core_data_resp_i [NUM_HARTS-1:0],

    // Interrupt inputs (one per hart)
    input  logic [31:0] irq_i [NUM_HARTS-1:0],

    // Debug Interface (one bit per hart).
    // PACKED [NUM_HARTS-1:0] (not an unpacked array): the SoC carries these
    // 1-bit-per-hart control signals packed (the TDU drives core_wake/core_sleep
    // packed + uses a bitwise NOT for core_running), so a packed port connects
    // straight through with no boundary adaptation. The earlier unpacked-array
    // ports forced a packed-to-unpacked conversion in the top whose per-index
    // cycle-based evaluation order dropped some bits (e.g. a worker's core_wake[h]
    // pulse was read stale, so that hart never woke). Internal per-hart usage is
    // a plain bit-select core_wake_i[HART_x], identical for packed or unpacked.
    input  logic [NUM_HARTS-1:0] debug_req_i,

    // Wake request (one bit per hart) — from the TDU / TITAN orchestrator.
    // Releases a worker core from its dormant (power-gated) reset state.
    input  logic [NUM_HARTS-1:0] core_wake_i,

    // sleep (one bit per hart)
    output logic [NUM_HARTS-1:0] core_sleep_o
);

  // Intermediate signals per core
  logic [31:0] irq [NUM_HARTS];
  logic        debug_req [NUM_HARTS];
  logic        core_sleep [NUM_HARTS];
  logic        irq_ack [NUM_HARTS];
  logic [4:0]  irq_id [NUM_HARTS];

  genvar g, i;
  generate

  % for g_idx, group in enumerate(cpus):
    % for inst in range(group.count):

    // ═══════════════════════════════════════════════════════════════
    // Core ${g_idx}.${inst}: ${group.name} (${group.role}, hart ${group.hart_id_base + inst})
    // params: ${group.params}
    // ═══════════════════════════════════════════════════════════════

    localparam int HART_${g_idx}_${inst} = ${group.hart_id_base + inst};
    logic fetch_enable_${g_idx}_${inst};
      % if group.role == "titan":
    // TITAN orchestrator boots immediately out of reset.
    assign fetch_enable_${g_idx}_${inst} = 1'b1;
      % else:
    // Worker core (${group.role}): held dormant out of reset and released by a
    // TDU/orchestrator wake pulse on core_wake_i — this closes the
    // TDU.core_wake_o -> fetch_enable loop. Latch: once woken, stays running.
    logic core_run_${g_idx}_${inst};
    always_ff @(posedge clk_i or negedge rst_ni) begin
      if (!rst_ni) core_run_${g_idx}_${inst} <= 1'b0;
      else if (core_wake_i[HART_${g_idx}_${inst}]) core_run_${g_idx}_${inst} <= 1'b1;
    end
    assign fetch_enable_${g_idx}_${inst} = core_run_${g_idx}_${inst};
      % endif

      % if group.name == "cv32e20":

    <%
    cv32e20_params = _cv32e20_params(group.cpu, xif)
    %>

    // CORE-V-XIF interface instance. cve2_xif_wrapper drives this interface
    // unconditionally, so it must be a real instance (an unconnected interface
    // port is illegal — "Interface port not connected"). The PoC attaches no
    // coprocessor, so the eXtension-unit side of the interface simply dangles.
    if_xif #() xif_${g_idx}_${inst} ();

    cve2_xif_wrapper #(
${",\n".join(cv32e20_params)}
    ) cpu_${g_idx}_${inst} (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .test_en_i(1'b0),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .boot_addr_i(BOOT_ADDR),
        .dm_exception_addr_i(32'h0),
        .dm_halt_addr_i(DM_HALTADDRESS),

        .instr_addr_o  (core_instr_req_o[HART_${g_idx}_${inst}].addr),
        .instr_req_o   (core_instr_req_o[HART_${g_idx}_${inst}].req),
        .instr_rdata_i (core_instr_resp_i[HART_${g_idx}_${inst}].rdata),
        .instr_gnt_i   (core_instr_resp_i[HART_${g_idx}_${inst}].gnt),
        .instr_rvalid_i(core_instr_resp_i[HART_${g_idx}_${inst}].rvalid),

        .data_addr_o  (core_data_req_o[HART_${g_idx}_${inst}].addr),
        .data_wdata_o (core_data_req_o[HART_${g_idx}_${inst}].wdata),
        .data_we_o    (core_data_req_o[HART_${g_idx}_${inst}].we),
        .data_req_o   (core_data_req_o[HART_${g_idx}_${inst}].req),
        .data_be_o    (core_data_req_o[HART_${g_idx}_${inst}].be),
        .data_rdata_i (core_data_resp_i[HART_${g_idx}_${inst}].rdata),
        .data_gnt_i   (core_data_resp_i[HART_${g_idx}_${inst}].gnt),
        .data_rvalid_i(core_data_resp_i[HART_${g_idx}_${inst}].rvalid),

        .irq_software_i(irq_i[HART_${g_idx}_${inst}][3]),
        .irq_timer_i   (irq_i[HART_${g_idx}_${inst}][7]),
        .irq_external_i(irq_i[HART_${g_idx}_${inst}][11]),
        .irq_fast_i    (irq_i[HART_${g_idx}_${inst}][31:16]),

        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),
        .debug_halted_o(),

        // CORE-V-XIF (interface present; no coprocessor attached)
        .xif_compressed_if(xif_${g_idx}_${inst}),
        .xif_issue_if     (xif_${g_idx}_${inst}),
        .xif_commit_if    (xif_${g_idx}_${inst}),
        .xif_mem_if       (xif_${g_idx}_${inst}),
        .xif_mem_result_if(xif_${g_idx}_${inst}),
        .xif_result_if    (xif_${g_idx}_${inst}),

        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}])
    );

      % elif group.name == "cv32e40x":

    <%
    cv32e40x_params = _cv32e40x_params(group.cpu, xif)
    %>

    // CORE-V-XIF interface instance (present even when no coprocessor is
    // attached — the core drives it unconditionally; unconnected interface
    // ports are illegal). Named cv32e40x_if_xif since the post-0.10 vendor
    // bump (upstream renamed if_xif).
    cv32e40x_if_xif #() xif_${g_idx}_${inst} ();

    cv32e40x_core #(
${",\n".join(cv32e40x_params)}
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),
        .scan_cg_en_i(1'b0),

        .boot_addr_i(BOOT_ADDR),
        .dm_exception_addr_i(32'h0),
        .dm_halt_addr_i(DM_HALTADDRESS),
        .mhartid_i(hart_id_i[HART_${g_idx}_${inst}]),
        .mimpid_patch_i(4'h0),
        .mtvec_addr_i(32'h0),

        .instr_req_o    (core_instr_req_o[HART_${g_idx}_${inst}].req),
        .instr_gnt_i    (core_instr_resp_i[HART_${g_idx}_${inst}].gnt),
        .instr_rvalid_i (core_instr_resp_i[HART_${g_idx}_${inst}].rvalid),
        .instr_addr_o   (core_instr_req_o[HART_${g_idx}_${inst}].addr),
        .instr_memtype_o(),
        .instr_prot_o   (),
        .instr_dbg_o    (),
        .instr_rdata_i  (core_instr_resp_i[HART_${g_idx}_${inst}].rdata),
        .instr_err_i    (1'b0),

        .data_req_o    (core_data_req_o[HART_${g_idx}_${inst}].req),
        .data_gnt_i    (core_data_resp_i[HART_${g_idx}_${inst}].gnt),
        .data_rvalid_i (core_data_resp_i[HART_${g_idx}_${inst}].rvalid),
        .data_addr_o   (core_data_req_o[HART_${g_idx}_${inst}].addr),
        .data_be_o     (core_data_req_o[HART_${g_idx}_${inst}].be),
        .data_we_o     (core_data_req_o[HART_${g_idx}_${inst}].we),
        .data_wdata_o  (core_data_req_o[HART_${g_idx}_${inst}].wdata),
        .data_memtype_o(),
        .data_prot_o   (),
        .data_dbg_o    (),
        .data_atop_o   (),
        .data_rdata_i  (core_data_resp_i[HART_${g_idx}_${inst}].rdata),
        .data_err_i    (1'b0),
        .data_exokay_i (1'b1),

        .mcycle_o(),

        .time_i(64'h0),

        // CORE-V-XIF (interface present; no coprocessor attached)
        .xif_compressed_if(xif_${g_idx}_${inst}),
        .xif_issue_if     (xif_${g_idx}_${inst}),
        .xif_commit_if    (xif_${g_idx}_${inst}),
        .xif_mem_if       (xif_${g_idx}_${inst}),
        .xif_mem_result_if(xif_${g_idx}_${inst}),
        .xif_result_if    (xif_${g_idx}_${inst}),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),

        .wu_wfe_i(1'b0),

        .clic_irq_i      (),
        .clic_irq_id_i   (),
        .clic_irq_level_i(),
        .clic_irq_priv_i (),
        .clic_irq_shv_i  (),

        .fencei_flush_req_o(),
        .fencei_flush_ack_i(1'b1),

        .debug_req_i      (debug_req_i[HART_${g_idx}_${inst}]),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),
        .debug_pc_valid_o (),
        .debug_pc_o       (),

        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}])
    );

      % elif group.name == "cv32e40px":

    import cv32e40px_core_v_xif_pkg::*;

    <%
    cv32e40px_params = _cv32e40px_params(group.cpu, xif)
    %>

    // CORE-V-XIF interface instance (present even when no coprocessor is
    // attached — the wrapper drives it unconditionally; unconnected interface
    // ports are illegal).
    if_xif #() xif_${g_idx}_${inst} ();

    cv32e40px_xif_wrapper #(
${",\n".join(cv32e40px_params)}
    ) cpu_${g_idx}_${inst} (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .pulp_clock_en_i(1'b1),
        .scan_cg_en_i   (1'b0),

        .boot_addr_i        (BOOT_ADDR),
        .mtvec_addr_i       (32'h0),
        .dm_halt_addr_i     (DM_HALTADDRESS),
        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .dm_exception_addr_i(32'h0),

        .instr_addr_o  (core_instr_req_o[HART_${g_idx}_${inst}].addr),
        .instr_req_o   (core_instr_req_o[HART_${g_idx}_${inst}].req),
        .instr_rdata_i (core_instr_resp_i[HART_${g_idx}_${inst}].rdata),
        .instr_gnt_i   (core_instr_resp_i[HART_${g_idx}_${inst}].gnt),
        .instr_rvalid_i(core_instr_resp_i[HART_${g_idx}_${inst}].rvalid),

        .data_addr_o  (core_data_req_o[HART_${g_idx}_${inst}].addr),
        .data_wdata_o (core_data_req_o[HART_${g_idx}_${inst}].wdata),
        .data_we_o    (core_data_req_o[HART_${g_idx}_${inst}].we),
        .data_req_o   (core_data_req_o[HART_${g_idx}_${inst}].req),
        .data_be_o    (core_data_req_o[HART_${g_idx}_${inst}].be),
        .data_rdata_i (core_data_resp_i[HART_${g_idx}_${inst}].rdata),
        .data_gnt_i   (core_data_resp_i[HART_${g_idx}_${inst}].gnt),
        .data_rvalid_i(core_data_resp_i[HART_${g_idx}_${inst}].rvalid),

        // CORE-V-XIF (interface present; no coprocessor attached)
        .xif_compressed_if(xif_${g_idx}_${inst}),
        .xif_issue_if     (xif_${g_idx}_${inst}),
        .xif_commit_if    (xif_${g_idx}_${inst}),
        .xif_mem_if       (xif_${g_idx}_${inst}),
        .xif_mem_result_if(xif_${g_idx}_${inst}),
        .xif_result_if    (xif_${g_idx}_${inst}),

        .irq_i    (irq_i[HART_${g_idx}_${inst}]),
        .irq_ack_o(),
        .irq_id_o (),

        .debug_req_i      (debug_req_i[HART_${g_idx}_${inst}]),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),

        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}])
    );

      % elif group.name == "fazyrv":

    // ─── FazyRV via SCI wrapper (Wishbone Classic → OBI) ────────
    fazyrv_sci #(
        .CHUNKSIZE(${group.params.get('chunksize', 8)}),
        .CONF_STR("${group.params.get('conf', 'CSR')}"),
        ## FazyRV requires a BRAM register-file implementation when CSRs are
        ## enabled (CONF=CSR); LOGIC is only valid for MIN/INT. Default to the
        ## wrapper's own default (BRAM_DP_BP) so the CSR default is consistent.
        .RFTYPE_STR("${group.params.get('rftype', 'BRAM_DP_BP')}"),
        .RVC_STR("${group.params.get('rvc', 'NONE')}"),
        .MEMDLY1(${group.params.get('memdly1', 0)}),
        ## Per-core reset/boot address from the mosaic config (default 0x180).
        ## Lets each woken worker run its own program; int(str(..),0) accepts a
        ## YAML int (0x1000 -> 4096) or a quoted hex string.
        .BOOTADR(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .boot_addr_i(BOOT_ADDR),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        .instr_req_o(core_instr_req_o[HART_${g_idx}_${inst}]),
        .instr_resp_i(core_instr_resp_i[HART_${g_idx}_${inst}]),
        .data_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .data_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

      % elif group.name == "serv":

    // ─── SERV via SCI wrapper (Wishbone Lite → OBI, unified) ────
    // SERV uses a single unified OBI port (data channel) for both
    // instruction fetch and data access. The instr channel is unused.
    serv_sci #(
        .W(${group.params.get('w', 1)}),
        .WITH_CSR(${group.params.get('with_csr', 1)}),
        .COMPRESSED(${group.params.get('compressed', 0)}),
        .MDU(${group.params.get('mdu', 0)}),
        .PRE_REGISTER(${group.params.get('pre_register', 0)}),
        ## Per-core reset address from the mosaic config (default 0x180) — lets a
        ## woken worker run its own program (int(str(..),0) accepts int or hex str).
        .RESET_PC(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        // Unified OBI port → data channel (handles both I+D)
        .mem_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .mem_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

    // Instruction channel: tied off (SERV uses unified bus)
    assign core_instr_req_o[HART_${g_idx}_${inst}] = '0;

      % elif group.name == "picorv32":

    // ─── PicoRV32 via SCI wrapper (native mem port → OBI, unified) ──
    // PicoRV32 fetches and loads/stores over one native memory port, so
    // like SERV it uses a single unified OBI port (data channel).
    picorv32_sci #(
        .ENABLE_COUNTERS(${group.params.get('counters', 0)}),
        .BARREL_SHIFTER(${group.params.get('barrel_shifter', 0)}),
        .COMPRESSED_ISA(${group.params.get('compressed', 0)}),
        .ENABLE_MUL(${group.params.get('mul', 0)}),
        .ENABLE_DIV(${group.params.get('div', 0)}),
        ## Per-core reset address from the mosaic config (default 0x180) — lets a
        ## woken worker run its own program (int(str(..),0) accepts int or hex str).
        .PROGADDR_RESET(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        // Unified OBI port → data channel (handles both I+D)
        .mem_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .mem_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

    // Instruction channel: tied off (PicoRV32 uses unified bus)
    assign core_instr_req_o[HART_${g_idx}_${inst}] = '0;

      % elif group.name == "cva6":

    // ─── CVA6 (32-bit, SIM-ONLY) via SCI wrapper (AXI4 → OBI, unified) ──
    // cv32a65x-derived config (M-mode, WT cache, uncached data side); the
    // wrapper folds the burst-capable AXI→OBI bridge. All traffic on one
    // unified OBI port (data channel). EXCLUDED from the GF180 tapeout.
    cva6_sci #(
        ## Per-core reset address from the mosaic config (default 0x180).
        .BOOT_ADDR(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        // Unified OBI port → data channel (all core traffic via the bridge)
        .mem_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .mem_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

    // Instruction channel: tied off (CVA6 uses the unified bridge port)
    assign core_instr_req_o[HART_${g_idx}_${inst}] = '0;

      % elif group.name == "snitch":

    // ─── Snitch via SCI wrapper (instr refill + TCDM reqrsp → split OBI) ──
    // Bare mempool-flavor Snitch integer core. The wrapper converts the
    // instruction refill port and the TCDM q/p data port to split OBI
    // (writes get no p-channel response — handled inside snitch_sci).
    snitch_sci #(
        ## Per-core reset address from the mosaic config (default 0x180) — lets a
        ## woken worker run its own program (int(str(..),0) accepts int or hex str).
        .BOOT_ADDR(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)}),
        .RVE(${group.params.get('rve', 0)}),
        .RVM(${group.params.get('rvm', 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        .instr_req_o(core_instr_req_o[HART_${g_idx}_${inst}]),
        .instr_resp_i(core_instr_resp_i[HART_${g_idx}_${inst}]),
        .data_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .data_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

      % elif group.name == "qerv":

    // ─── QERV via SERV SCI wrapper (Wishbone Lite → OBI, unified) ──
    // QERV is the nibble-serial (W=4) sibling of SERV. It reuses the
    // same vendored servile/serv stack (hw/vendor/mosaic/serv) and the
    // W-parameterized serv_sci wrapper, with the datapath width set to 4.
    // Like SERV it presents a single unified OBI port (data channel).
    serv_sci #(
        .W(${group.params.get('w', 4)}),
        .WITH_CSR(${group.params.get('with_csr', 1)}),
        .COMPRESSED(${group.params.get('compressed', 0)}),
        .MDU(${group.params.get('mdu', 0)}),
        .PRE_REGISTER(${group.params.get('pre_register', 0)}),
        ## Per-core reset address from the mosaic config (default 0x180) — lets a
        ## woken worker run its own program (int(str(..),0) accepts int or hex str).
        .RESET_PC(32'h${'%08x' % int(str(group.params.get('boot_addr', 0x180)), 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        // Unified OBI port → data channel (handles both I+D)
        .mem_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .mem_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

    // Instruction channel: tied off (QERV uses unified bus)
    assign core_instr_req_o[HART_${g_idx}_${inst}] = '0;

      % elif group.name == "ibex":

    // ─── Ibex via SCI wrapper (req/gnt → OBI, split I+D) ──────────
    // Ibex has independent instruction and data ports (like cv32e20), so
    // both OBI master channels are driven — no tie-off.
    ibex_sci #(
        .RV32E(${1 if group.params.get('rv32e', False) else 0}),
        .MHPMCounterNum(${group.params.get('mhpmcounters', 0)})
    ) cpu_${g_idx}_${inst} (
        .clk_i(clk_i),
        .rst_ni(rst_ni),

        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .boot_addr_i(BOOT_ADDR),
        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}]),

        .irq_i(irq_i[HART_${g_idx}_${inst}]),
        .debug_req_i(debug_req_i[HART_${g_idx}_${inst}]),

        .instr_req_o(core_instr_req_o[HART_${g_idx}_${inst}]),
        .instr_resp_i(core_instr_resp_i[HART_${g_idx}_${inst}]),
        .data_req_o(core_data_req_o[HART_${g_idx}_${inst}]),
        .data_resp_i(core_data_resp_i[HART_${g_idx}_${inst}])
    );

      % else:

      // Unknown core type '${group.name}' — compile error
      // To add a new core: write an SCI wrapper + add a branch above
      // Unsupported error: instantiate a dummy that will fail lint
      // to alert the user
      // TODO: Add SCI for ${group.name}

    cv32e40p_top #(
${",\n".join(cv32e40p_params)}
    ) cpu_${g_idx}_${inst} (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .pulp_clock_en_i(1'b1),
        .scan_cg_en_i   (1'b0),

        .boot_addr_i        (BOOT_ADDR),
        .mtvec_addr_i       (32'h0),
        .dm_halt_addr_i     (DM_HALTADDRESS),
        .hart_id_i(hart_id_i[HART_${g_idx}_${inst}]),
        .dm_exception_addr_i(32'h0),

        .instr_addr_o  (core_instr_req_o[HART_${g_idx}_${inst}].addr),
        .instr_req_o   (core_instr_req_o[HART_${g_idx}_${inst}].req),
        .instr_rdata_i (core_instr_resp_i[HART_${g_idx}_${inst}].rdata),
        .instr_gnt_i   (core_instr_resp_i[HART_${g_idx}_${inst}].gnt),
        .instr_rvalid_i(core_instr_resp_i[HART_${g_idx}_${inst}].rvalid),

        .data_addr_o  (core_data_req_o[HART_${g_idx}_${inst}].addr),
        .data_wdata_o (core_data_req_o[HART_${g_idx}_${inst}].wdata),
        .data_we_o    (core_data_req_o[HART_${g_idx}_${inst}].we),
        .data_req_o   (core_data_req_o[HART_${g_idx}_${inst}].req),
        .data_be_o    (core_data_req_o[HART_${g_idx}_${inst}].be),
        .data_rdata_i (core_data_resp_i[HART_${g_idx}_${inst}].rdata),
        .data_gnt_i   (core_data_resp_i[HART_${g_idx}_${inst}].gnt),
        .data_rvalid_i(core_data_resp_i[HART_${g_idx}_${inst}].rvalid),

        .irq_i    (irq_i[HART_${g_idx}_${inst}]),
        .irq_ack_o(),
        .irq_id_o (),

        .debug_req_i      (debug_req_i[HART_${g_idx}_${inst}]),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),

        .fetch_enable_i(fetch_enable_${g_idx}_${inst}),
        .core_sleep_o(core_sleep_o[HART_${g_idx}_${inst}])
    );

      % endif

    % endfor
  % endfor

  endgenerate

endmodule

% else:

// ─── Single-core cpu_subsystem (original backward-compat) ──────────
module cpu_subsystem
  import obi_pkg::*;
  import core_v_mini_mcu_pkg::*;
#(
    parameter BOOT_ADDR = 'h180,
    parameter DM_HALTADDRESS = '0
) (
    // Clock and Reset
    input logic clk_i,
    input logic rst_ni,

    // Core ID
    input logic [31:0] hart_id_i,

    // Instruction memory interface
    output obi_req_t  core_instr_req_o,
    input  obi_resp_t core_instr_resp_i,

    // Data memory interface
    output obi_req_t  core_data_req_o,
    input  obi_resp_t core_data_resp_i,

    // eXtension interface
    if_xif.cpu_compressed xif_compressed_if,
    if_xif.cpu_issue      xif_issue_if,
    if_xif.cpu_commit     xif_commit_if,
    if_xif.cpu_mem        xif_mem_if,
    if_xif.cpu_mem_result xif_mem_result_if,
    if_xif.cpu_result     xif_result_if,

    // Interrupt inputs
    input  logic [31:0] irq_i,
    output logic        irq_ack_o,
    output logic [ 4:0] irq_id_o,

    // Debug Interface
    input logic debug_req_i,

    // sleep
    output logic core_sleep_o
);

  // CPU Control Signals
  logic fetch_enable;
  assign fetch_enable = 1'b1;

  assign core_instr_req_o.wdata = '0;
  assign core_instr_req_o.we    = '0;
  assign core_instr_req_o.be    = 4'b1111;

% if cpu.name == "cv32e20":

<%
cv32e20_params = _cv32e20_params(cpu, xif)
%>

    cve2_xif_wrapper #(
${",\n".join(cv32e20_params)}
    ) cv32e20_i (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .test_en_i(1'b0),

        .hart_id_i,
        .boot_addr_i(BOOT_ADDR),
        .dm_exception_addr_i(32'h0),
        .dm_halt_addr_i(DM_HALTADDRESS),

        .instr_addr_o  (core_instr_req_o.addr),
        .instr_req_o   (core_instr_req_o.req),
        .instr_rdata_i (core_instr_resp_i.rdata),
        .instr_gnt_i   (core_instr_resp_i.gnt),
        .instr_rvalid_i(core_instr_resp_i.rvalid),

        .data_addr_o  (core_data_req_o.addr),
        .data_wdata_o (core_data_req_o.wdata),
        .data_we_o    (core_data_req_o.we),
        .data_req_o   (core_data_req_o.req),
        .data_be_o    (core_data_req_o.be),
        .data_rdata_i (core_data_resp_i.rdata),
        .data_gnt_i   (core_data_resp_i.gnt),
        .data_rvalid_i(core_data_resp_i.rvalid),

        .irq_software_i(irq_i[3]),
        .irq_timer_i   (irq_i[7]),
        .irq_external_i(irq_i[11]),
        .irq_fast_i    (irq_i[31:16]),

        .debug_req_i(debug_req_i),
        .debug_halted_o(),

        // CORE-V-XIF
        .xif_compressed_if,
        .xif_issue_if,
        .xif_commit_if,
        .xif_mem_if,
        .xif_mem_result_if,
        .xif_result_if,

        .fetch_enable_i(fetch_enable),
        .core_sleep_o
    );

    assign irq_ack_o = '0;
    assign irq_id_o  = '0;

% elif cpu.name == "cv32e40x":

<%
cv32e40x_params = _cv32e40x_params(cpu, xif)
%>

    cv32e40x_core #(
${",\n".join(cv32e40x_params)}
    ) cv32e40x_core_i (
        // Clock and reset
        .clk_i(clk_i),
        .rst_ni(rst_ni),
        .scan_cg_en_i(1'b0),

        // Static configuration
        .boot_addr_i(BOOT_ADDR),
        .dm_exception_addr_i(32'h0),
        .dm_halt_addr_i(DM_HALTADDRESS),
        .mhartid_i(32'h0),
        .mimpid_patch_i(4'h0),
        .mtvec_addr_i(32'h0),

        // Instruction memory interface
        .instr_req_o    (core_instr_req_o.req),
        .instr_gnt_i    (core_instr_resp_i.gnt),
        .instr_rvalid_i (core_instr_resp_i.rvalid),
        .instr_addr_o   (core_instr_req_o.addr),
        .instr_memtype_o(),
        .instr_prot_o   (),
        .instr_dbg_o    (),
        .instr_rdata_i  (core_instr_resp_i.rdata),
        .instr_err_i    (1'b0),

        // Data memory interface
        .data_req_o    (core_data_req_o.req),
        .data_gnt_i    (core_data_resp_i.gnt),
        .data_rvalid_i (core_data_resp_i.rvalid),
        .data_addr_o   (core_data_req_o.addr),
        .data_be_o     (core_data_req_o.be),
        .data_we_o     (core_data_req_o.we),
        .data_wdata_o  (core_data_req_o.wdata),
        .data_memtype_o(),
        .data_prot_o   (),
        .data_dbg_o    (),
        .data_atop_o   (),
        .data_rdata_i  (core_data_resp_i.rdata),
        .data_err_i    (1'b0),
        .data_exokay_i (1'b1),

        // Cycle count
        .mcycle_o(),

        // Time input
        .time_i(64'h0),

        // eXtension interface
        .xif_compressed_if,
        .xif_issue_if,
        .xif_commit_if,
        .xif_mem_if,
        .xif_mem_result_if,
        .xif_result_if,

        // Basic interrupt architecture
        .irq_i(irq_i),

        // Event wakeup signal
        .wu_wfe_i(1'b0),

        // Smclic interrupt architecture
        .clic_irq_i      (),
        .clic_irq_id_i   (),
        .clic_irq_level_i(),
        .clic_irq_priv_i (),
        .clic_irq_shv_i  (),

        // Fence.i flush handshake
        .fencei_flush_req_o(),
        .fencei_flush_ack_i(1'b1),

        // Debug interface
        .debug_req_i      (debug_req_i),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),
        .debug_pc_valid_o (),
        .debug_pc_o       (),

        // CPU control signals
        .fetch_enable_i(fetch_enable),
        .core_sleep_o
    );

    assign irq_ack_o = '0;
    assign irq_id_o  = '0;

% elif cpu.name == "cv32e40px":

    import cv32e40px_core_v_xif_pkg::*;

<%
cv32e40px_params = _cv32e40px_params(cpu, xif)
%>

    cv32e40px_xif_wrapper #(
${",\n".join(cv32e40px_params)}
    ) cv32e40px_xif_wrapper_i (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .pulp_clock_en_i(1'b1),
        .scan_cg_en_i   (1'b0),

        .boot_addr_i        (BOOT_ADDR),
        .mtvec_addr_i       (32'h0),
        .dm_halt_addr_i     (DM_HALTADDRESS),
        .hart_id_i,
        .dm_exception_addr_i(32'h0),

        .instr_addr_o  (core_instr_req_o.addr),
        .instr_req_o   (core_instr_req_o.req),
        .instr_rdata_i (core_instr_resp_i.rdata),
        .instr_gnt_i   (core_instr_resp_i.gnt),
        .instr_rvalid_i(core_instr_resp_i.rvalid),

        .data_addr_o  (core_data_req_o.addr),
        .data_wdata_o (core_data_req_o.wdata),
        .data_we_o    (core_data_req_o.we),
        .data_req_o   (core_data_req_o.req),
        .data_be_o    (core_data_req_o.be),
        .data_rdata_i (core_data_resp_i.rdata),
        .data_gnt_i   (core_data_resp_i.gnt),
        .data_rvalid_i(core_data_resp_i.rvalid),

        // CORE-V-XIF
        .xif_compressed_if,
        .xif_issue_if,
        .xif_commit_if,
        .xif_mem_if,
        .xif_mem_result_if,
        .xif_result_if,

        .irq_i    (irq_i),
        .irq_ack_o(irq_ack_o),
        .irq_id_o (irq_id_o),

        .debug_req_i      (debug_req_i),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),

        .fetch_enable_i(fetch_enable),
        .core_sleep_o

    );

% else:

<%
cv32e40p_params = _cv32e40p_params(cpu, xif)
%>

    cv32e40p_top #(
${",\n".join(cv32e40p_params)}
    ) cv32e40p_top_i (
        .clk_i (clk_i),
        .rst_ni(rst_ni),

        .pulp_clock_en_i(1'b1),
        .scan_cg_en_i   (1'b0),

        .boot_addr_i        (BOOT_ADDR),
        .mtvec_addr_i       (32'h0),
        .dm_halt_addr_i     (DM_HALTADDRESS),
        .hart_id_i,
        .dm_exception_addr_i(32'h0),

        .instr_addr_o  (core_instr_req_o.addr),
        .instr_req_o   (core_instr_req_o.req),
        .instr_rdata_i (core_instr_resp_i.rdata),
        .instr_gnt_i   (core_instr_resp_i.gnt),
        .instr_rvalid_i(core_instr_resp_i.rvalid),

        .data_addr_o  (core_data_req_o.addr),
        .data_wdata_o (core_data_req_o.wdata),
        .data_we_o    (core_data_req_o.we),
        .data_req_o   (core_data_req_o.req),
        .data_be_o    (core_data_req_o.be),
        .data_rdata_i (core_data_resp_i.rdata),
        .data_gnt_i   (core_data_resp_i.gnt),
        .data_rvalid_i(core_data_resp_i.rvalid),

        .irq_i    (irq_i),
        .irq_ack_o(irq_ack_o),
        .irq_id_o (irq_id_o),

        .debug_req_i      (debug_req_i),
        .debug_havereset_o(),
        .debug_running_o  (),
        .debug_halted_o   (),

        .fetch_enable_i(fetch_enable),
        .core_sleep_o
    );

% endif

endmodule

% endif
