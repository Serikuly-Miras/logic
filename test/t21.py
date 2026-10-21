# top = tis100::t21

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, ReadOnly
from spade import SpadeExt

SLOTS = 15
PORTS = ["Up", "Down", "Left", "Right"]
NO_INS = "[None, None, None, None]"
NO_READY = "[false, false, false, false]"


def on(port, value, default):
    return "[" + ", ".join(value if p == port else default for p in PORTS) + "]"


def ins(port, v):
    return on(port, f"Some({v})", "None")


def ready(port):
    return on(port, "true", "false")


async def load(s, dut, instrs, length=None):
    # Write one slot per cycle, then set len. Caller decides whether run is low.
    for slot, instr in enumerate(instrs):
        s.i.write = f"Some(({slot}, {instr}))"
        await FallingEdge(dut.clk_i)
    s.i.write = "None"
    s.i.len_write = f"Some({len(instrs) if length is None else length})"
    await FallingEdge(dut.clk_i)
    s.i.len_write = "None"


async def setup(dut, *instrs, length=None):
    s = SpadeExt(dut)
    s.i.write, s.i.len_write = "None", "None"
    s.i.ins, s.i.out_ready = NO_INS, NO_READY
    s.i.rst, s.i.run = "true", "false"
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    await FallingEdge(dut.clk_i)
    s.i.rst = "false"
    await load(s, dut, instrs, length)
    s.i.run = "true"
    return s


async def cycles(dut, n):
    for _ in range(n):
        await FallingEdge(dut.clk_i)


@cocotb.test()
async def empty_node_idles(dut):
    s = await setup(dut)
    await cycles(dut, 5)
    s.o.acc.assert_eq("0")
    s.o.bak.assert_eq("0")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def single_instruction_loops(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))")
    await cycles(dut, 3)
    s.o.acc.assert_eq("3")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def pc_steps_and_wraps(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(1))",
        "Instr::Add(Src::Imm(10))",
        "Instr::Add(Src::Imm(100))",
    )
    s.o.pc.assert_eq("0")
    await cycles(dut, 1)
    s.o.pc.assert_eq("1")
    s.o.acc.assert_eq("1")
    await cycles(dut, 2)
    s.o.pc.assert_eq("0")
    s.o.acc.assert_eq("111")
    await cycles(dut, 1)
    s.o.acc.assert_eq("112")


@cocotb.test()
async def slots_past_len_never_run(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(1))",
        "Instr::Add(Src::Imm(2))",
        "Instr::Add(Src::Imm(500))",
        length=2,
    )
    await cycles(dut, 6)
    s.o.acc.assert_eq("9")


@cocotb.test()
async def stop_restarts_program(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))", "Instr::Add(Src::Imm(10))")
    await cycles(dut, 3)
    s.o.acc.assert_eq("12")
    s.i.run = "false"
    await cycles(dut, 1)
    s.o.acc.assert_eq("0")
    s.o.pc.assert_eq("0")
    s.i.run = "true"
    await cycles(dut, 2)
    s.o.acc.assert_eq("11")


@cocotb.test()
async def reload_replaces_program(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))", "Instr::Add(Src::Imm(1))")
    await cycles(dut, 2)
    s.i.run = "false"
    await load(s, dut, ["Instr::Sub(Src::Imm(5))"])
    s.i.run = "true"
    await cycles(dut, 3)
    s.o.acc.assert_eq("-15")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def rst_clears_program(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))")
    await cycles(dut, 2)
    s.i.rst = "true"
    await cycles(dut, 1)
    s.i.rst = "false"
    await cycles(dut, 3)
    s.o.acc.assert_eq("0")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def full_program_uses_all_15_slots(dut):
    s = await setup(dut, *["Instr::Add(Src::Imm(1))"] * SLOTS)
    await cycles(dut, SLOTS - 1)
    s.o.pc.assert_eq(str(SLOTS - 1))
    await cycles(dut, 1)
    s.o.pc.assert_eq("0")
    s.o.acc.assert_eq(str(SLOTS))


@cocotb.test()
async def add_sub(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(5))", "Instr::Sub(Src::Imm(8))")
    await cycles(dut, 2)
    s.o.acc.assert_eq("-3")


@cocotb.test()
async def saturates_high(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(990))", "Instr::Add(Src::Imm(20))")
    await cycles(dut, 2)
    s.o.acc.assert_eq("999")


@cocotb.test()
async def saturates_low(dut):
    s = await setup(dut, "Instr::Sub(Src::Imm(990))", "Instr::Sub(Src::Imm(20))")
    await cycles(dut, 2)
    s.o.acc.assert_eq("-999")


@cocotb.test()
async def neg(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(42))", "Instr::Neg", "Instr::Neg")
    await cycles(dut, 2)
    s.o.acc.assert_eq("-42")
    await cycles(dut, 1)
    s.o.acc.assert_eq("42")


@cocotb.test()
async def sav_copies_acc(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(42))", "Instr::Sav", "Instr::Add(Src::Imm(1))"
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("43")
    s.o.bak.assert_eq("42")


@cocotb.test()
async def swp_swaps(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(7))",
        "Instr::Sav",
        "Instr::Add(Src::Imm(3))",
        "Instr::Swp",
        "Instr::Swp",
    )
    await cycles(dut, 4)
    s.o.acc.assert_eq("7")
    s.o.bak.assert_eq("10")
    await cycles(dut, 1)
    s.o.acc.assert_eq("10")
    s.o.bak.assert_eq("7")


@cocotb.test()
async def jmp(dut):
    # Slot 2 is never reached.
    s = await setup(
        dut, "Instr::Add(Src::Imm(1))", "Instr::Jmp(0)", "Instr::Add(Src::Imm(100))"
    )
    await cycles(dut, 6)
    s.o.acc.assert_eq("3")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def jmp_to_self_halts(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))", "Instr::Jmp(1)")
    await cycles(dut, 10)
    s.o.acc.assert_eq("1")
    s.o.pc.assert_eq("1")


@cocotb.test()
async def jez_taken_then_not(dut):
    s = await setup(
        dut, "Instr::Jez(2)", "Instr::Add(Src::Imm(100))", "Instr::Add(Src::Imm(1))"
    )
    await cycles(dut, 1)
    s.o.pc.assert_eq("2")
    await cycles(dut, 1)
    s.o.acc.assert_eq("1")
    await cycles(dut, 1)
    s.o.pc.assert_eq("1")
    await cycles(dut, 2)
    s.o.acc.assert_eq("102")


@cocotb.test()
async def jnz_countdown(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(3))",
        "Instr::Sub(Src::Imm(1))",
        "Instr::Jnz(1)",
        "Instr::Add(Src::Imm(100))",
        "Instr::Jmp(4)",
    )
    await cycles(dut, 7)
    s.o.acc.assert_eq("0")
    s.o.pc.assert_eq("3")
    await cycles(dut, 5)
    s.o.acc.assert_eq("100")
    s.o.pc.assert_eq("4")


@cocotb.test()
async def jgz(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(5))",
        "Instr::Jgz(3)",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("6")


@cocotb.test()
async def jlz(dut):
    s = await setup(
        dut,
        "Instr::Sub(Src::Imm(5))",
        "Instr::Jlz(3)",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("-4")


@cocotb.test()
async def jgz_jlz_not_taken_on_zero(dut):
    s = await setup(
        dut,
        "Instr::Jgz(3)",
        "Instr::Jlz(3)",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("100")


@cocotb.test()
async def jro_forward(dut):
    s = await setup(
        dut,
        "Instr::Jro(Src::Imm(2))",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
    )
    await cycles(dut, 1)
    s.o.pc.assert_eq("2")
    await cycles(dut, 1)
    s.o.acc.assert_eq("1")


@cocotb.test()
async def jro_clamps_to_first_slot(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))", "Instr::Jro(Src::Imm(-5))")
    await cycles(dut, 2)
    s.o.pc.assert_eq("0")


@cocotb.test()
async def jro_clamps_to_last_slot(dut):
    s = await setup(
        dut,
        "Instr::Jro(Src::Imm(10))",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
    )
    await cycles(dut, 1)
    s.o.pc.assert_eq("2")


@cocotb.test()
async def jro_zero_halts(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(1))", "Instr::Jro(Src::Imm(0))")
    await cycles(dut, 10)
    s.o.acc.assert_eq("1")
    s.o.pc.assert_eq("1")


@cocotb.test()
async def add_acc_doubles(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(3))", "Instr::Add(Src::Acc)", "Instr::Jmp(2)"
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("6")


@cocotb.test()
async def add_acc_saturates(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(600))", "Instr::Add(Src::Acc)", "Instr::Jmp(2)"
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("999")


@cocotb.test()
async def sub_acc_zeroes(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(42))", "Instr::Sub(Src::Acc)", "Instr::Jmp(2)"
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("0")


@cocotb.test()
async def nil_reads_zero(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(5))", "Instr::Add(Src::Nil)", "Instr::Sub(Src::Nil)"
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("5")


@cocotb.test()
async def jro_acc_jump_table(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(2))",
        "Instr::Jro(Src::Acc)",
        "Instr::Add(Src::Imm(100))",
        "Instr::Add(Src::Imm(1))",
        "Instr::Jmp(4)",
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("3")
    s.o.pc.assert_eq("4")


@cocotb.test()
async def jro_acc_negative_clamps(dut):
    # acc = -1: back to 0. Next round acc = -2: clamped to 0.
    s = await setup(dut, "Instr::Sub(Src::Imm(1))", "Instr::Jro(Src::Acc)")
    await cycles(dut, 2)
    s.o.pc.assert_eq("0")
    await cycles(dut, 2)
    s.o.acc.assert_eq("-2")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def mov_imm_acc(dut):
    s = await setup(
        dut, "Instr::Add(Src::Imm(5))", "Instr::Mov(Src::Imm(-42), Dst::Acc)"
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("-42")
    s.o.pc.assert_eq("0")


@cocotb.test()
async def mov_nil_acc_clears(dut):
    s = await setup(dut, "Instr::Add(Src::Imm(5))", "Instr::Mov(Src::Nil, Dst::Acc)")
    await cycles(dut, 1)
    s.o.acc.assert_eq("5")
    await cycles(dut, 1)
    s.o.acc.assert_eq("0")


@cocotb.test()
async def mov_acc_acc_keeps(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(7))",
        "Instr::Mov(Src::Acc, Dst::Acc)",
        "Instr::Jmp(2)",
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("7")


@cocotb.test()
async def mov_to_nil_discards(dut):
    s = await setup(
        dut,
        "Instr::Add(Src::Imm(7))",
        "Instr::Mov(Src::Imm(500), Dst::Nil)",
        "Instr::Jmp(2)",
    )
    await cycles(dut, 2)
    s.o.acc.assert_eq("7")
    s.o.bak.assert_eq("0")
    s.o.pc.assert_eq("2")


# --- Ports ---


async def settle():
    await ReadOnly()


async def restart(s, dut, *instrs):
    await FallingEdge(dut.clk_i)
    s.i.ins, s.i.out_ready = NO_INS, NO_READY
    s.i.rst, s.i.run = "true", "false"
    await cycles(dut, 1)
    s.i.rst = "false"
    await load(s, dut, instrs)
    s.i.run = "true"


def src(port):
    return f"Src::Port(Port::{port})"


def dst(port):
    return f"Dst::Port(Port::{port})"


@cocotb.test()
async def mov_port_acc_blocks_until_value(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(
            s, dut, f"Instr::Mov({src(port)}, Dst::Acc)", "Instr::Add(Src::Imm(1))"
        )
        await cycles(dut, 3)
        s.o.pc.assert_eq("0")
        s.o.in_ready.assert_eq(ready(port))

        s.i.ins = ins(port, 42)
        await cycles(dut, 1)
        s.i.ins = NO_INS
        s.o.acc.assert_eq("42")
        s.o.pc.assert_eq("1")
        await settle()
        s.o.in_ready.assert_eq(NO_READY)


@cocotb.test()
async def other_ports_do_not_unblock(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Mov({src(port)}, Dst::Acc)")
        s.i.ins = (
            "[" + ", ".join("None" if p == port else "Some(7)" for p in PORTS) + "]"
        )
        await cycles(dut, 3)
        s.o.pc.assert_eq("0")
        s.o.acc.assert_eq("0")


@cocotb.test()
async def add_port_consumes_stream(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Add({src(port)})")
        for v, gap in [(5, 2), (-3, 0), (10, 1)]:
            await cycles(dut, gap)
            s.i.ins = ins(port, v)
            await cycles(dut, 1)
            s.i.ins = NO_INS
        s.o.acc.assert_eq("12")


@cocotb.test()
async def mov_acc_port_waits_for_reader(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(
            s,
            dut,
            "Instr::Add(Src::Imm(7))",
            f"Instr::Mov(Src::Acc, {dst(port)})",
            "Instr::Add(Src::Imm(1))",
        )
        await cycles(dut, 1)
        s.o.outs.assert_eq(NO_INS)
        await cycles(dut, 1)
        s.o.outs.assert_eq(ins(port, 7))

        # Ready on the wrong ports does nothing.
        s.i.out_ready = (
            "[" + ", ".join("false" if p == port else "true" for p in PORTS) + "]"
        )
        await cycles(dut, 3)
        s.o.outs.assert_eq(ins(port, 7))
        s.o.pc.assert_eq("1")
        s.o.acc.assert_eq("7")

        s.i.out_ready = ready(port)
        await cycles(dut, 1)
        s.i.out_ready = NO_READY
        s.o.outs.assert_eq(NO_INS)
        s.o.pc.assert_eq("2")
        await cycles(dut, 1)
        s.o.acc.assert_eq("8")


@cocotb.test()
async def mov_imm_port(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Mov(Src::Imm(-5), {dst(port)})", "Instr::Jmp(1)")
        s.i.out_ready = ready(port)
        await cycles(dut, 1)
        s.o.outs.assert_eq(ins(port, -5))
        await cycles(dut, 1)
        s.o.outs.assert_eq(NO_INS)
        s.o.pc.assert_eq("1")


@cocotb.test()
async def mov_port_to_other_port(dut):
    # MOV LEFT, RIGHT etc.: read phase, then write phase.
    s = await setup(dut)
    for a, b in [
        ("Up", "Down"),
        ("Down", "Up"),
        ("Left", "Right"),
        ("Right", "Left"),
        ("Up", "Up"),
    ]:
        await restart(s, dut, f"Instr::Mov({src(a)}, {dst(b)})", "Instr::Jmp(1)")
        s.i.ins = ins(a, 9)
        await cycles(dut, 1)
        s.i.ins = NO_INS
        s.o.outs.assert_eq(ins(b, 9))
        await settle()
        s.o.in_ready.assert_eq(NO_READY)

        await cycles(dut, 1)  # leave ReadOnly; the write keeps waiting meanwhile
        s.o.outs.assert_eq(ins(b, 9))
        s.i.out_ready = ready(b)
        await cycles(dut, 1)
        s.i.out_ready = NO_READY
        s.o.outs.assert_eq(NO_INS)
        s.o.pc.assert_eq("1")


@cocotb.test()
async def mov_port_nil_consumes(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Mov({src(port)}, Dst::Nil)", "Instr::Jmp(1)")
        await cycles(dut, 2)
        s.o.pc.assert_eq("0")
        s.i.ins = ins(port, 100)
        await cycles(dut, 1)
        s.i.ins = NO_INS
        s.o.pc.assert_eq("1")
        s.o.acc.assert_eq("0")


@cocotb.test()
async def jro_port(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(
            s,
            dut,
            f"Instr::Jro({src(port)})",
            "Instr::Add(Src::Imm(100))",
            "Instr::Add(Src::Imm(1))",
        )
        s.i.ins = ins(port, 2)
        await cycles(dut, 1)
        s.i.ins = NO_INS
        s.o.pc.assert_eq("2")


@cocotb.test()
async def stop_drops_pending_write(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Mov(Src::Imm(3), {dst(port)})")
        await cycles(dut, 2)
        s.o.outs.assert_eq(ins(port, 3))
        s.i.run = "false"
        await cycles(dut, 1)
        s.o.outs.assert_eq(NO_INS)
        s.o.pc.assert_eq("0")


@cocotb.test()
async def no_ready_while_stopped(dut):
    s = await setup(dut)
    for port in PORTS:
        await restart(s, dut, f"Instr::Mov({src(port)}, Dst::Acc)")
        s.i.run = "false"
        await settle()
        s.o.in_ready.assert_eq(NO_READY)


# --- ANY / LAST ---


def all_ins(values):
    # values: dict port -> value; others None.
    return (
        "["
        + ", ".join(f"Some({values[p]})" if p in values else "None" for p in PORTS)
        + "]"
    )


@cocotb.test()
async def any_read_priority(dut):
    # Reading ANY picks LEFT, RIGHT, UP, DOWN in that order, and only takes one value.
    s = await setup(dut)
    cases = [
        ({"Up": 1, "Down": 2, "Left": 3, "Right": 4}, "Left"),
        ({"Up": 1, "Down": 2, "Right": 4}, "Right"),
        ({"Up": 1, "Down": 2}, "Up"),
        ({"Down": 2}, "Down"),
    ]
    for values, winner in cases:
        await restart(s, dut, "Instr::Mov(Src::Any, Dst::Acc)", "Instr::Jmp(1)")
        s.i.ins = all_ins(values)
        await settle()
        s.o.in_ready.assert_eq(ready(winner))
        await cycles(dut, 1)
        s.i.ins = NO_INS
        s.o.acc.assert_eq(str(values[winner]))
        s.o.pc.assert_eq("1")


@cocotb.test()
async def any_read_blocks_until_any_value(dut):
    s = await setup(dut)
    await restart(s, dut, "Instr::Add(Src::Any)")
    await cycles(dut, 3)
    s.o.pc.assert_eq("0")
    s.o.acc.assert_eq("0")
    s.o.in_ready.assert_eq(NO_READY)
    s.i.ins = ins("Down", 6)
    await cycles(dut, 1)
    s.i.ins = NO_INS
    s.o.acc.assert_eq("6")


@cocotb.test()
async def any_write_rotates_until_taken(dut):
    s = await setup(dut)
    await restart(s, dut, "Instr::Mov(Src::Imm(5), Dst::Any)", "Instr::Jmp(1)")
    await cycles(dut, 1)  # latch
    for port in ["Up", "Left", "Right", "Down", "Up"]:
        s.o.outs.assert_eq(ins(port, 5))
        await cycles(dut, 1)
    # Only the RIGHT neighbour reads: LEFT is skipped, RIGHT takes it.
    s.o.outs.assert_eq(ins("Left", 5))
    s.i.out_ready = ready("Right")
    await cycles(dut, 1)
    s.o.outs.assert_eq(ins("Right", 5))
    s.o.pc.assert_eq("0")
    await cycles(dut, 1)
    s.i.out_ready = NO_READY
    s.o.outs.assert_eq(NO_INS)
    s.o.pc.assert_eq("1")


@cocotb.test()
async def any_write_goes_to_one_reader(dut):
    s = await setup(dut)
    await restart(s, dut, "Instr::Mov(Src::Imm(5), Dst::Any)", "Instr::Jmp(1)")
    s.i.out_ready = "[true, true, true, true]"
    await cycles(dut, 1)  # latch
    s.o.outs.assert_eq(ins("Up", 5))  # offered on exactly one port
    await cycles(dut, 1)
    s.o.outs.assert_eq(NO_INS)
    s.o.pc.assert_eq("1")


@cocotb.test()
async def last_after_any_read(dut):
    s = await setup(dut)
    await restart(
        s,
        dut,
        "Instr::Mov(Src::Any, Dst::Acc)",
        "Instr::Add(Src::Last)",
        "Instr::Jmp(2)",
    )
    s.i.ins = ins("Right", 10)
    await cycles(dut, 1)
    s.i.ins = NO_INS
    s.o.acc.assert_eq("10")
    # ADD LAST now waits on RIGHT only.
    s.i.ins = ins("Left", 99)
    await settle()
    s.o.in_ready.assert_eq(ready("Right"))
    await cycles(dut, 2)
    s.o.pc.assert_eq("1")
    s.i.ins = ins("Right", 5)
    await cycles(dut, 1)
    s.i.ins = NO_INS
    s.o.acc.assert_eq("15")


@cocotb.test()
async def last_after_any_write(dut):
    s = await setup(dut)
    await restart(
        s,
        dut,
        "Instr::Mov(Src::Imm(1), Dst::Any)",
        "Instr::Mov(Src::Imm(2), Dst::Last)",
        "Instr::Jmp(2)",
    )
    s.i.out_ready = ready("Left")
    await cycles(dut, 3)  # latch, offer UP, offer LEFT -> taken
    s.o.pc.assert_eq("1")
    s.i.out_ready = NO_READY
    await cycles(dut, 1)  # latch
    s.o.outs.assert_eq(ins("Left", 2))
    await cycles(dut, 3)
    s.o.outs.assert_eq(ins("Left", 2))  # LAST does not rotate


@cocotb.test()
async def last_before_any_is_nil(dut):
    s = await setup(dut)
    await restart(
        s,
        dut,
        "Instr::Add(Src::Imm(5))",
        "Instr::Add(Src::Last)",
        "Instr::Mov(Src::Imm(3), Dst::Last)",
        "Instr::Jmp(3)",
    )
    await cycles(dut, 3)
    s.o.acc.assert_eq("5")
    s.o.pc.assert_eq("3")
    s.o.outs.assert_eq(NO_INS)
