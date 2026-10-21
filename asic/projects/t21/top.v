module t21 (
    input         clk_i,
    input         rst_i,
    input         run_i,
    // Spade-encoded values, passed through unchanged:
    //   write_i:     Option<(uint<4>, Instr)>
    //   len_write_i: Option<uint<4>>
    //   ins_i:       [Option<int<11>>; 4]  (Up, Down, Left, Right)
    //   out_ready_i: [bool; 4]
    input  [27:0] write_i,
    input  [4:0]  len_write_i,
    input  [47:0] ins_i,
    input  [3:0]  out_ready_i,
    output [10:0] acc_o,
    output [10:0] bak_o,
    output [3:0]  pc_o,
    output [3:0]  in_ready_o,      // [bool; 4]
    output [47:0] outs_o           // [Option<int<11>>; 4]
);
    wire [77:0] out;

    \logic::tis100::t21  u_t21 (
        .clk_i(clk_i),
        .rst_i(rst_i),
        .run_i(run_i),
        .write_i(write_i),
        .len_write_i(len_write_i),
        .ins_i(ins_i),
        .out_ready_i(out_ready_i),
        .output__(out)
    );

    // T21Out is packed first field -> MSB
    assign acc_o      = out[77:67];
    assign bak_o      = out[66:56];
    assign pc_o       = out[55:52];
    assign in_ready_o = out[51:48];
    assign outs_o     = out[47:0];
endmodule
