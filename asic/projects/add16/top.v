module add16 (
    input         clk_i,
    input  [15:0] a_i,
    input  [15:0] b_i,
    output [15:0] sum_o
);
    \logic::add16::add16  u_add16 (
        .clk_i(clk_i),
        .a_i(a_i),
        .b_i(b_i),
        .output__(sum_o)
    );
endmodule
