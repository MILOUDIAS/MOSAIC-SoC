// tb_idma_xbar_mem.sv — shared single-port memory with 2→1 arbitration, for the
// SoC-level iDMA test. Unlike the per-block dual-port memory, the iDMA's read and
// write masters here CONTEND for one memory (write priority), modelling the way
// the SoC's system crossbar serialises the iDMA's two masters onto the shared
// SRAM. A correct iDMA must still complete the copy under this back-pressure.

module tb_idma_xbar_mem #(
    parameter int unsigned DEPTH_WORDS = 4096
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    input  obi_pkg::obi_req_t  rd_req_i,
    output obi_pkg::obi_resp_t rd_resp_o,
    input  obi_pkg::obi_req_t  wr_req_i,
    output obi_pkg::obi_resp_t wr_resp_o
);
  localparam int unsigned AW = $clog2(DEPTH_WORDS);
  logic [31:0] mem[DEPTH_WORDS];

  function automatic int unsigned widx(input logic [31:0] a);
    return a[AW+1:2];
  endfunction

  // Single-outstanding shared port: one transaction in flight at a time.
  logic        busy;
  logic        sel_wr;  // 1 = serving write master, 0 = serving read
  logic [31:0] addr_q;

  wire         serve_wr = ~busy & wr_req_i.req;  // write priority
  wire         serve_rd = ~busy & ~wr_req_i.req & rd_req_i.req;

  // Responses: gnt + rvalid pulse for the selected master in the busy cycle.
  assign rd_resp_o.gnt    = busy & ~sel_wr;
  assign rd_resp_o.rvalid = busy & ~sel_wr;
  assign rd_resp_o.rdata  = mem[widx(addr_q)];
  assign wr_resp_o.gnt    = busy &  sel_wr;
  assign wr_resp_o.rvalid = busy &  sel_wr;
  assign wr_resp_o.rdata  = mem[widx(addr_q)];

  always_ff @(posedge clk_i) begin
    if (!rst_ni) begin
      busy   <= 1'b0;
      sel_wr <= 1'b0;
    end else if (busy) begin
      busy <= 1'b0;  // 1-cycle response, then free for the next transaction
    end else if (serve_wr) begin
      busy   <= 1'b1;
      sel_wr <= 1'b1;
      addr_q <= wr_req_i.addr;
      if (wr_req_i.we) begin
        if (wr_req_i.be[0]) mem[widx(wr_req_i.addr)][7:0] <= wr_req_i.wdata[7:0];
        if (wr_req_i.be[1]) mem[widx(wr_req_i.addr)][15:8] <= wr_req_i.wdata[15:8];
        if (wr_req_i.be[2]) mem[widx(wr_req_i.addr)][23:16] <= wr_req_i.wdata[23:16];
        if (wr_req_i.be[3]) mem[widx(wr_req_i.addr)][31:24] <= wr_req_i.wdata[31:24];
      end
    end else if (serve_rd) begin
      busy   <= 1'b1;
      sel_wr <= 1'b0;
      addr_q <= rd_req_i.addr;
    end
  end
endmodule
