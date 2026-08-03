// Gate-level testbench for the Chipathon Block A macro.
//
// WHY THIS EXISTS
// ---------------
// Every simulation up to now ran on RTL. This one runs on the POST-PLACE-AND-
// ROUTE netlist -- the actual gates in the GDS, with the PDK's own cell models
// -- and optionally with SDF timing back-annotated. It closes the last item the
// schematic review listed for the physical phase ("post-synthesis gate-level
// simulation once a netlist exists").
//
// It also verifies something no RTL testbench can: that synthesis, CTS, place
// and route preserved the design's behaviour. Bugs 28 and 31 were both cases of
// RTL that elaborated and simulated happily while being wrong; this is the
// complementary check, RTL-correct-but-implementation-broken.
//
// THE INTERFACE IS THE CHIP'S
// ---------------------------
// This drives only the 22 pins the MPW integrator will bond. There is no
// backdoor memory load, no hierarchical force, no probing of internal state --
// the design boots XIP from a behavioural QSPI flash and reports through
// status_valid_o/status_o, which with soc.debug: false is the only observability
// the silicon has. If this passes, the part can be brought up on a board the
// same way.
//
// Usage (see run_gls.sh):
//   +firmware=<hex>   flash image, Verilog hex from objcopy -O verilog
//   +sdf=<file>       optional SDF for timing-annotated GLS
//   +maxcycles=<n>    watchdog

`timescale 1ns / 1ps

module gls_tb;

  // 10 MHz -- the frequency the macro is hardened at (CLOCK_PERIOD 100 ns).
  // Running GLS faster than the design was closed for would be meaningless.
  localparam realtime ClkPeriod = 100.0;

  logic       clk = 1'b0;
  logic       rst_n = 1'b0;
  logic       boot_select = 1'b1;        // 1 = boot from flash
  logic       execute_from_flash = 1'b1; // 1 = XIP through the spimemio window
  logic       uart_rx = 1'b1;            // idle high; nothing drives us
  wire        uart_tx;
  wire        spi_sck;
  wire        spi_csb;
  wire [3:0]  spi_sd;
  wire        status_valid;
  wire [6:0]  status;

  // The netlist instantiates every cell with .VDD/.VNW/.VPW/.VSS, so the models
  // are compiled with USE_POWER_PINS and the top's power pins must be driven.
  supply1 VDD;
  supply0 VSS;

  string  firmware;
  string  sdf_file;
  int     maxcycles;
  longint cycles;

  mosaic_block_a dut (
      .clk_i               (clk),
      .rst_ni              (rst_n),
      .boot_select_i       (boot_select),
      .execute_from_flash_i(execute_from_flash),
      .uart_rx_i           (uart_rx),
      .uart_tx_o           (uart_tx),
      .spi_flash_sck_o     (spi_sck),
      .spi_flash_cs_o      (spi_csb),
      .spi_flash_sd_io     (spi_sd),
      .status_valid_o      (status_valid),
      .status_o            (status),
      .VDD                 (VDD),
      .VSS                 (VSS)
  );

  spiflash flash_i (
      .csb(spi_csb),
      .clk(spi_sck),
      .io0(spi_sd[0]),
      .io1(spi_sd[1]),
      .io2(spi_sd[2]),
      .io3(spi_sd[3])
  );

  always #(ClkPeriod / 2.0) clk = ~clk;

  // Count cycles for the watchdog and for reporting how long boot took.
  always @(posedge clk) cycles <= cycles + 1;

  initial begin
    cycles = 0;

    if (!$value$plusargs("firmware=%s", firmware)) begin
      $display("[GLS] FATAL: +firmware=<hex> is required");
      $fatal(1);
    end
    if (!$value$plusargs("maxcycles=%d", maxcycles)) maxcycles = 2_000_000;

    // SDF is optional: without it this is a zero-delay functional check of the
    // routed netlist; with it, the cell and interconnect delays of a corner are
    // back-annotated and the run also exercises setup/hold in the models.
    if ($value$plusargs("sdf=%s", sdf_file)) begin
      $display("[GLS] annotating SDF: %s", sdf_file);
      $sdf_annotate(sdf_file, dut);
    end else begin
      $display("[GLS] zero-delay run (no SDF)");
    end

    // Load the flash exactly as tb_util.svh does for the RTL flow: clear, then
    // read the Verilog-hex image with its @address records.
    for (int unsigned i = 0; i < 16 * 1024 * 1024; i++) flash_i.memory[i] = 8'h00;
    $readmemh(firmware, flash_i.memory);
    $display("[GLS] flash image: %s", firmware);

    // Reset for 20 cycles.
    rst_n = 1'b0;
    repeat (20) @(posedge clk);
    rst_n = 1'b1;
    $display("[GLS] reset released at %t", $time);
  end

  // Model power-up: every flop gets a defined value at time 0. The generated
  // file explains why this is modelling silicon rather than hiding a problem.
`ifndef GLS_NO_POWERUP_INIT
`include "gls_powerup_init.svh"
`endif

  // ---- pass / fail -------------------------------------------------------
  // status_valid_o is the exit strobe driven from soc_ctrl; status_o[6:0] is
  // the exit value. This is precisely what a bring-up board would watch.
  always @(posedge clk) begin
    if (rst_n && status_valid) begin
      $display("[GLS] status_valid_o asserted at %t after %0d cycles, status_o = 0x%02h",
               $time, cycles, status);
      if (status == 7'd0) begin
        $display("### RESULT: EXIT SUCCESS — gate-level netlist booted and reported 0");
      end else begin
        $display("### RESULT: FAIL — exit value 0x%02h", status);
      end
      $finish;
    end
  end

  // Watchdog. A hang here is a real failure: the RTL reaches the exit register
  // in ~12 400 cycles, so anything approaching the limit means the netlist does
  // not do what the RTL did.
  always @(posedge clk) begin
    if (cycles > maxcycles) begin
      $display("[GLS] status_o = 0x%02h, status_valid_o = %b", status, status_valid);
      $display("### RESULT: FAIL — watchdog at %0d cycles without status_valid_o", cycles);
      $finish;
    end
  end

  // Progress, so a long run is visibly alive rather than apparently wedged.
  always @(posedge clk) begin
    if (cycles % 2000 == 0 && cycles > 0)
      $display("[GLS] %0d cycles, t=%t, sck=%b csb=%b sd=%h", cycles, $time,
               spi_sck, spi_csb, spi_sd);
  end

endmodule
