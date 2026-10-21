# top = tis100::board

import re

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly
from spade import SpadeExt

NODES = 12
COLS = 4
SLOTS = 15
NO_INS = "[None, None, None, None]"
NO_READY = "[false, false, false, false]"


def arr(items):
    return "[" + ", ".join(items) + "]"


def outs(regs):
    return arr(
        f"T21Out({acc}, {bak}, {pc}, {NO_READY}, {NO_INS})" for acc, bak, pc in regs
    )


def options(field):
    return [
        int(v) if v else None
        for v in re.findall(r"Some\((-?\d+)\)|None", field.value())
    ]


def bools(field):
    return [b == "true" for b in re.findall(r"true|false", field.value())]


async def setup(dut, programs):
    programs = [programs.get(i, []) for i in range(NODES)]
    s = SpadeExt(dut)
    s.i.writes = arr(["None"] * NODES)
    s.i.len_writes = arr(["None"] * NODES)
    s.i.top_ins, s.i.bottom_ins = NO_INS, NO_INS
    s.i.top_out_ready, s.i.bottom_out_ready = NO_READY, NO_READY
    s.i.rst, s.i.run = "true", "false"
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    await FallingEdge(dut.clk_i)
    s.i.rst = "false"
    for slot in range(SLOTS):
        s.i.writes = arr(
            f"Some(({slot}, {p[slot]}))" if slot < len(p) else "None" for p in programs
        )
        await FallingEdge(dut.clk_i)
    s.i.writes = arr(["None"] * NODES)
    s.i.len_writes = arr(f"Some({len(p)})" for p in programs)
    await FallingEdge(dut.clk_i)
    s.i.len_writes = arr(["None"] * NODES)
    s.i.run = "true"
    return s


async def stream(s, dut, values, col_in, col_out, max_cycles=500):
    pending = list(values)
    got = []
    s.i.bottom_out_ready = arr("true" if c == col_out else "false" for c in range(COLS))
    for _ in range(max_cycles):
        s.i.top_ins = arr(
            f"Some({pending[0]})" if pending and c == col_in else "None"
            for c in range(COLS)
        )
        await ReadOnly()
        taken = bool(pending) and bools(s.o.top_in_ready)[col_in]
        out = options(s.o.bottom_outs)[col_out]
        await FallingEdge(dut.clk_i)
        if taken:
            pending.pop(0)
        if out is not None:
            got.append(out)
        if len(got) == len(values):
            break
    s.i.top_ins = NO_INS
    s.i.bottom_out_ready = NO_READY
    return got


def mov(src, dst):
    return f"Instr::Mov({src}, {dst})"


UP, DOWN, LEFT, RIGHT, ANY = (
    "Src::Port(Port::Up)",
    "Src::Port(Port::Down)",
    "Src::Port(Port::Left)",
    "Src::Port(Port::Right)",
    "Src::Any",
)
D_UP, D_DOWN, D_LEFT, D_RIGHT, D_ANY = (
    "Dst::Port(Port::Up)",
    "Dst::Port(Port::Down)",
    "Dst::Port(Port::Left)",
    "Dst::Port(Port::Right)",
    "Dst::Any",
)
PASS_DOWN = [mov(UP, D_DOWN)]
VALUES = [1, 2, 3, -5, 999, -999, 0, 42]


@cocotb.test()
async def all_zero_after_reset(dut):
    s = await setup(dut, {})
    s.o.nodes.assert_eq(outs([(0, 0, 0)] * NODES))


@cocotb.test()
async def nodes_run_their_own_programs(dut):
    programs = {
        i: [f"Instr::Add(Src::Imm({i}))", "Instr::Sav"] for i in range(0, NODES, 2)
    }
    s = await setup(dut, programs)
    await FallingEdge(dut.clk_i)
    await FallingEdge(dut.clk_i)
    s.o.nodes.assert_eq(outs([(0, 0, 0) if i % 2 else (i, i, 0) for i in range(NODES)]))


@cocotb.test()
async def column_passthrough(dut):
    s = await setup(dut, {0: PASS_DOWN, 4: PASS_DOWN, 8: PASS_DOWN})
    got = await stream(s, dut, VALUES, col_in=0, col_out=0)
    assert got == VALUES, got


@cocotb.test()
async def every_column_passthrough(dut):
    s = await setup(dut, {i: PASS_DOWN for i in range(NODES)})
    for col in range(COLS):
        got = await stream(s, dut, VALUES, col_in=col, col_out=col)
        assert got == VALUES, (col, got)


@cocotb.test()
async def doubler(dut):
    s = await setup(
        dut,
        {
            0: [mov(UP, "Dst::Acc"), "Instr::Add(Src::Acc)", mov("Src::Acc", D_DOWN)],
            4: PASS_DOWN,
            8: PASS_DOWN,
        },
    )
    got = await stream(s, dut, [1, 2, 3, -7, 600], col_in=0, col_out=0)
    assert got == [2, 4, 6, -14, 999], got


@cocotb.test()
async def route_across_the_top_row(dut):
    # In at column 0, right along row 0, out at column 3.
    s = await setup(
        dut,
        {
            0: [mov(UP, D_RIGHT)],
            1: [mov(LEFT, D_RIGHT)],
            2: [mov(LEFT, D_RIGHT)],
            3: [mov(LEFT, D_DOWN)],
            7: PASS_DOWN,
            11: PASS_DOWN,
        },
    )
    got = await stream(s, dut, VALUES, col_in=0, col_out=3)
    assert got == VALUES, got


@cocotb.test()
async def route_back_left(dut):
    # In at column 3, left along row 1, out at column 0.
    s = await setup(
        dut,
        {
            3: PASS_DOWN,
            7: [mov(UP, D_LEFT)],
            6: [mov(RIGHT, D_LEFT)],
            5: [mov(RIGHT, D_LEFT)],
            4: [mov(RIGHT, D_DOWN)],
            8: PASS_DOWN,
        },
    )
    got = await stream(s, dut, VALUES, col_in=3, col_out=0)
    assert got == VALUES, got


@cocotb.test()
async def round_trip_on_one_link(dut):
    # n0 sends each value right to n1, n1 adds 1 and sends it back left.
    s = await setup(
        dut,
        {
            0: [mov(UP, D_RIGHT), mov(RIGHT, D_DOWN)],
            1: [
                mov(LEFT, "Dst::Acc"),
                "Instr::Add(Src::Imm(1))",
                mov("Src::Acc", D_LEFT),
            ],
            4: PASS_DOWN,
            8: PASS_DOWN,
        },
    )
    got = await stream(s, dut, VALUES, col_in=0, col_out=0)
    assert got == [min(v + 1, 999) for v in VALUES], got


@cocotb.test()
async def any_finds_the_reader(dut):
    # n0 writes ANY; only n4 below is reading, so everything goes down.
    s = await setup(dut, {0: [mov(UP, D_ANY)], 4: PASS_DOWN, 8: PASS_DOWN})
    got = await stream(s, dut, VALUES, col_in=0, col_out=0)
    assert got == VALUES, got


@cocotb.test()
async def any_read_merges_two_inputs(dut):
    # Columns 0 and 1 both feed n5; n5 reads ANY and sends down column 1.
    s = await setup(
        dut,
        {
            0: PASS_DOWN,
            4: [mov(UP, D_RIGHT)],
            1: PASS_DOWN,
            5: [mov(ANY, D_DOWN)],
            9: PASS_DOWN,
        },
    )
    got = await stream(s, dut, [10, 20, 30], col_in=0, col_out=1)
    assert got == [10, 20, 30], got
    got = await stream(s, dut, [-1, -2], col_in=1, col_out=1)
    assert got == [-1, -2], got
