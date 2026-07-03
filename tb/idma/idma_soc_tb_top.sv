// idma_soc_tb_top.sv — SoC-level iDMA test top.
//
// Same as idma_tb_top, but the iDMA's read and write masters share ONE
// arbitrated single-port memory (tb_idma_xbar_mem) instead of a dual-port one —
// modelling the SoC system crossbar serialising the iDMA's two masters onto the
// shared SRAM. A correct iDMA must still complete the copy under this bus
// contention. Driven by the same cocotb test (test_idma) via the flat reg bus.

module idma_soc_tb_top (
    input  logic        clk_i,
    input  logic        rst_ni,
    input  logic [31:0] reg_addr_i,
    input  logic [31:0] reg_wdata_i,
    input  logic        reg_write_i,
    input  logic        reg_valid_i,
    output logic        reg_ready_o,
    output logic [31:0] reg_rdata_o,
    output logic        dma_done_o,
    output logic        dma_done_intr_o
);
  import core_v_mini_mcu_pkg::*;

  reg_pkg::reg_req_t reg_req;
  reg_pkg::reg_rsp_t reg_rsp;
  always_comb begin
    reg_req       = '0;
    reg_req.addr  = reg_addr_i;
    reg_req.wdata = reg_wdata_i;
    reg_req.write = reg_write_i;
    reg_req.wstrb = 4'hF;
    reg_req.valid = reg_valid_i;
  end
  assign reg_ready_o = reg_rsp.ready;
  assign reg_rdata_o = reg_rsp.rdata;

  obi_pkg::obi_req_t [DMA_NUM_MASTER_PORTS-1:0] rd_req, wr_req, addr_req;
  obi_pkg::obi_resp_t [DMA_NUM_MASTER_PORTS-1:0] rd_resp, wr_resp, addr_resp;
  fifo_pkg::fifo_req_t  [DMA_CH_NUM-1:0] hw_fifo_req;
  fifo_pkg::fifo_resp_t [DMA_CH_NUM-1:0] hw_fifo_resp;
  logic [DMA_CH_NUM-1:0] dma_ready, dma_done;
  logic dma_window_intr;
  logic clk_gate_en_n   [DMA_CH_NUM];

  for (genvar i = 0; i < DMA_CH_NUM; i++) begin : gen_tie_ch
    assign hw_fifo_resp[i]  = '0;
    assign clk_gate_en_n[i] = 1'b1;
  end
  for (genvar i = 0; i < DMA_NUM_MASTER_PORTS; i++) begin : gen_tie_addr
    assign addr_resp[i] = '0;
  end
  for (genvar i = 1; i < DMA_NUM_MASTER_PORTS; i++) begin : gen_tie_rw
    assign rd_resp[i] = '0;
    assign wr_resp[i] = '0;
  end

  idma_xheep_wrapper #(
      .reg_req_t  (reg_pkg::reg_req_t),
      .reg_rsp_t  (reg_pkg::reg_rsp_t),
      .obi_req_t  (obi_pkg::obi_req_t),
      .obi_resp_t (obi_pkg::obi_resp_t),
      .fifo_req_t (fifo_pkg::fifo_req_t),
      .fifo_resp_t(fifo_pkg::fifo_resp_t),
      .GLOBAL_SLOT_NUM(1),
      .EXT_SLOT_NUM   (1)
  ) dut (
      .clk_i,
      .rst_ni,
      .clk_gate_en_ni       (clk_gate_en_n),
      .reg_req_i            (reg_req),
      .reg_rsp_o            (reg_rsp),
      .dma_read_req_o       (rd_req),
      .dma_read_resp_i      (rd_resp),
      .dma_write_req_o      (wr_req),
      .dma_write_resp_i     (wr_resp),
      .dma_addr_req_o       (addr_req),
      .dma_addr_resp_i      (addr_resp),
      .hw_fifo_req_o        (hw_fifo_req),
      .hw_fifo_resp_i       (hw_fifo_resp),
      .external_hw2reg_i    ('0),
      .global_trigger_slot_i('0),
      .ext_trigger_slot_i   ('0),
      .ext_dma_stop_i       ('0),
      .hw_fifo_done_i       ('0),
      .dma_done_intr_o      (dma_done_intr_o),
      .dma_window_intr_o    (dma_window_intr),
      .dma_ready_o          (dma_ready),
      .dma_done_o           (dma_done)
  );
  assign dma_done_o = dma_done[0];

  // Shared, arbitrated single-port memory (SoC bus model).
  tb_idma_xbar_mem #(
      .DEPTH_WORDS(4096)
  ) i_mem (
      .clk_i,
      .rst_ni,
      .rd_req_i (rd_req[0]),
      .rd_resp_o(rd_resp[0]),
      .wr_req_i (wr_req[0]),
      .wr_resp_o(wr_resp[0])
  );
endmodule
