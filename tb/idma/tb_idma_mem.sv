// tb_idma_mem.sv — dual-port behavioral memory for the iDMA per-block test.
// One read OBI port (iDMA read master) and one write OBI port (iDMA write
// master) share a single backing array, so an iDMA src→dst copy moves data
// within this memory. Registered single-outstanding handshake (gnt + rvalid
// together one cycle after accept), matching the OBI slaves the iDMA expects.

module tb_idma_mem #(
    parameter int unsigned DEPTH_WORDS = 4096
) (
    input  logic               clk_i,
    input  logic               rst_ni,
    // read master port
    input  obi_pkg::obi_req_t  rd_req_i,
    output obi_pkg::obi_resp_t rd_resp_o,
    // write master port
    input  obi_pkg::obi_req_t  wr_req_i,
    output obi_pkg::obi_resp_t wr_resp_o
);
  localparam int unsigned AW = $clog2(DEPTH_WORDS);
  logic [31:0] mem[DEPTH_WORDS];

  function automatic int unsigned widx(input logic [31:0] a);
    return a[AW+1:2];
  endfunction

  // ── Read port ──────────────────────────────────────────────────
  logic rd_v;
  wire  rd_acc = rd_req_i.req & ~rd_v;
  assign rd_resp_o.gnt    = rd_v;
  assign rd_resp_o.rvalid = rd_v;
  assign rd_resp_o.rdata  = mem[widx(rd_req_i.addr)];
  always_ff @(posedge clk_i) begin
    if (!rst_ni) rd_v <= 1'b0;
    else rd_v <= rd_acc;
  end

  // ── Write port (the only writer of `mem`) ──────────────────────
  logic wr_v;
  wire  wr_acc = wr_req_i.req & ~wr_v;
  assign wr_resp_o.gnt    = wr_v;
  assign wr_resp_o.rvalid = wr_v;
  assign wr_resp_o.rdata  = mem[widx(wr_req_i.addr)];
  always_ff @(posedge clk_i) begin
    if (!rst_ni) wr_v <= 1'b0;
    else begin
      wr_v <= wr_acc;
      if (wr_acc && wr_req_i.we) begin
        if (wr_req_i.be[0]) mem[widx(wr_req_i.addr)][7:0] <= wr_req_i.wdata[7:0];
        if (wr_req_i.be[1]) mem[widx(wr_req_i.addr)][15:8] <= wr_req_i.wdata[15:8];
        if (wr_req_i.be[2]) mem[widx(wr_req_i.addr)][23:16] <= wr_req_i.wdata[23:16];
        if (wr_req_i.be[3]) mem[widx(wr_req_i.addr)][31:24] <= wr_req_i.wdata[31:24];
      end
    end
  end
endmodule
