module mul16 (
    input         clk_i,
    input  [15:0] a_i,
    input  [15:0] b_i,
    output [15:0] product_o
);
    \logic::mul::mul  u_mul (
        .clk_i(clk_i),
        .a_i(a_i),
        .b_i(b_i),
        .output__(product_o)
    );
endmodule
