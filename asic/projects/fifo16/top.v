module fifo16 (
    input         clk_i,
    input         rst_i,
    input         push_i,
    input  [15:0] data_i,
    input         pop_i,
    output [15:0] head_o,
    output        empty_o,
    output        full_o,
    output [4:0]  count_o,
    output        dropped_o
);
    wire [23:0] out;

    \logic::fifo16::fifo16  u_fifo16 (
        .clk_i(clk_i),
        .rst_i(rst_i),
        .push_i(push_i),
        .data_i(data_i),
        .pop_i(pop_i),
        .output__(out)
    );

    // FifoOut is packed first field -> MSB
    assign head_o    = out[23:8];
    assign empty_o   = out[7];
    assign full_o    = out[6];
    assign count_o   = out[5:1];
    assign dropped_o = out[0];
endmodule
