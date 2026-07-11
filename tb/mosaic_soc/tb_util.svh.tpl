// tb_util.svh — DPI-export-free shadow of tb/tb_util.svh for the MOSAIC full-SoC
// functional sim. IDENTICAL task bodies to the upstream file, but WITHOUT the
// `export "DPI-C" task ...;` declarations.
//
// Why: Verilator 5.047 mis-generates the DPI-export wrapper for `tb_loadHEX`
// (which has a 64 KB `logic [7:0] stimuli[MEM_SIZE]` local) — it emits
// `this->...stimuli[i]` inside a *non-member* C function ("invalid use of 'this'
// in non-member function"), so the C++ build fails. The exports are only needed
// when a C++ main (tb_top.cpp) calls these tasks over DPI. We instead drive the
// sim from the pure-SV `tb_top.sv` (Verilator --binary), which calls them as
// ordinary SV tasks — so dropping the `export` lines costs nothing and dodges
// the bug. This file is put first on the include path so testharness.sv's
// `\`include "tb_util.svh"` resolves here.
//
// This file is GENERATED from tb_util.svh.tpl (bank layout is config-dependent:
// count, sizes, and interleaving all come from the active mosaic config).

<%
    memory_ss = xheep.memory_ss()
%>\
`ifndef SYNTHESIS

import core_v_mini_mcu_pkg::*;

task tb_getMemSize;
  output int mem_size;
  mem_size = core_v_mini_mcu_pkg::MEM_SIZE;
endtask

task tb_readHEX;
  input string file;
  output logic [7:0] stimuli[core_v_mini_mcu_pkg::MEM_SIZE];
  $readmemh(file, stimuli);
endtask

task tb_loadHEX;
  input string file;
  logic [7:0] stimuli[core_v_mini_mcu_pkg::MEM_SIZE];
  int i, stimuli_base, w_addr, NumBytes;
  logic [31:0] addr;

  tb_readHEX(file, stimuli);
  tb_getMemSize(NumBytes);

`ifndef VERILATOR
  for (i = 0; i < NumBytes; i = i + 4) begin
    @(posedge x_heep_system_i.core_v_mini_mcu_i.clk_i);
    addr = i;
    #1;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_req_o = 1'b1;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_addr_o = addr;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_we_o = 1'b1;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_be_o = 4'b1111;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_wdata_o = {
      stimuli[i+3], stimuli[i+2], stimuli[i+1], stimuli[i]
    };
    while (!x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_gnt_i)
    @(posedge x_heep_system_i.core_v_mini_mcu_i.clk_i);
    #1;
    force x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_req_o = 1'b0;
    wait (x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_rvalid_i);
    #1;
  end
  release x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_req_o;
  release x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_addr_o;
  release x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_we_o;
  release x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_be_o;
  release x_heep_system_i.core_v_mini_mcu_i.debug_subsystem_i.dm_obi_top_i.master_wdata_o;
`else
% for bank in memory_ss.iter_ram_banks():
  for (i = ${bank.start_address()}; i < ${bank.end_address()}; i = i + 4) begin
    if (((i / 4) & ${2**bank.il_level()-1}) == ${bank.il_offset()}) begin
      w_addr = ((i / 4) >> ${bank.il_level()}) % ${bank.size()//4};
      tb_writetoSram${bank.name()}(w_addr, stimuli[i+3], stimuli[i+2], stimuli[i+1], stimuli[i]);
    end
  end
% endfor
`endif
endtask

% for bank in memory_ss.iter_ram_banks():
task tb_writetoSram${bank.name()};
  input int addr;
  input [7:0] val3;
  input [7:0] val2;
  input [7:0] val1;
  input [7:0] val0;
  x_heep_system_i.core_v_mini_mcu_i.memory_subsystem_i.ram${bank.name()}_i.tc_ram_i.sram[addr] = {
    val3, val2, val1, val0
  };
endtask

% endfor
task tb_set_exit_loop;
  x_heep_system_i.core_v_mini_mcu_i.ao_peripheral_subsystem_i.soc_ctrl_i.testbench_set_exit_loop[0] = 1'b1;
endtask
`endif

task load_flash_hex;
  input string firmware_file;
  int i;
  for (i = 0; i <= 16 * 1024 * 1024; i = i + 1)
    gen_USE_EXTERNAL_DEVICE_EXAMPLE.flash_boot_i.memory[i] = 8'h00;
  $readmemh(firmware_file, gen_USE_EXTERNAL_DEVICE_EXAMPLE.flash_boot_i.memory);
endtask
