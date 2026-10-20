# top = fifo16::fifo16

import random
from collections import deque

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, Timer
from spade import SpadeExt

DEPTH = 16


async def setup(dut):
    s = SpadeExt(dut)
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    s.i.push, s.i.pop, s.i.data = "false", "false", "0"
    s.i.rst = "true"
    await FallingEdge(dut.clk_i)
    s.i.rst = "false"
    return s


async def step(s, dut, push=False, pop=False, data=0):
    s.i.push = "true" if push else "false"
    s.i.pop = "true" if pop else "false"
    s.i.data = str(data)
    await FallingEdge(dut.clk_i)
    s.i.push, s.i.pop = "false", "false"


@cocotb.test()
async def empty_after_reset(dut):
    s = await setup(dut)
    s.o.empty.assert_eq("true")
    s.o.count.assert_eq("0")


@cocotb.test()
async def fifo_order(dut):
    s = await setup(dut)
    for v in [10, 20, 30]:
        await step(s, dut, push=True, data=v)
    s.o.count.assert_eq("3")
    for v in [10, 20, 30]:
        s.o.head.assert_eq(str(v))
        await step(s, dut, pop=True)
    s.o.empty.assert_eq("true")


@cocotb.test()
async def overflow_drops_oldest(dut):
    s = await setup(dut)
    for v in range(DEPTH):
        await step(s, dut, push=True, data=v)
    s.o.full.assert_eq("true")
    s.o.head.assert_eq("0")

    s.i.push, s.i.data = "true", "100"
    await Timer(1, "ns")
    s.o.dropped.assert_eq("true")
    await FallingEdge(dut.clk_i)
    s.i.push = "false"

    s.o.count.assert_eq(str(DEPTH))
    for v in list(range(1, DEPTH)) + [100]:
        s.o.head.assert_eq(str(v))
        await step(s, dut, pop=True)
    s.o.empty.assert_eq("true")


@cocotb.test()
async def push_pop_when_full_keeps_all(dut):
    s = await setup(dut)
    for v in range(DEPTH):
        await step(s, dut, push=True, data=v)
    s.i.push, s.i.pop, s.i.data = "true", "true", "200"
    await Timer(1, "ns")
    s.o.dropped.assert_eq("false")
    await FallingEdge(dut.clk_i)
    s.i.push, s.i.pop = "false", "false"
    s.o.count.assert_eq(str(DEPTH))
    s.o.head.assert_eq("1")


@cocotb.test()
async def pop_when_empty_is_ignored(dut):
    s = await setup(dut)
    await step(s, dut, pop=True)
    s.o.count.assert_eq("0")
    await step(s, dut, push=True, data=7)
    s.o.head.assert_eq("7")


@cocotb.test()
async def random_vs_model(dut):
    s = await setup(dut)
    seed = random.randrange(2**32)
    dut._log.info(f"seed = {seed}")
    rng = random.Random(seed)
    model = deque(maxlen=DEPTH)

    for _ in range(2000):
        push = rng.random() < 0.6
        pop = rng.random() < 0.4
        data = rng.randrange(2**16)
        s.i.push = "true" if push else "false"
        s.i.pop = "true" if pop else "false"
        s.i.data = str(data)
        await Timer(1, "ns")

        s.o.count.assert_eq(str(len(model)))
        s.o.empty.assert_eq("true" if len(model) == 0 else "false")
        s.o.full.assert_eq("true" if len(model) == DEPTH else "false")
        if model:
            s.o.head.assert_eq(str(model[0]))
        dropped = push and len(model) == DEPTH and not pop
        s.o.dropped.assert_eq("true" if dropped else "false")

        await FallingEdge(dut.clk_i)
        if pop and model:
            model.popleft()
        if push:
            model.append(data)
