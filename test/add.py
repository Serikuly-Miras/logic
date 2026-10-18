# top = add::add

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from spade import SpadeExt

INT32_MIN = -(2**31)
INT32_MAX = 2**31 - 1


async def setup(dut):
    s = SpadeExt(dut)
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    await FallingEdge(dut.clk_i)
    return s


async def check_sum(s, dut, a, b):
    s.i.a, s.i.b = str(a), str(b)
    await FallingEdge(dut.clk_i)
    s.o.sum.assert_eq(str(a + b))


@cocotb.test()
async def zero(dut):
    s = await setup(dut)
    await check_sum(s, dut, 0, 0)
    await check_sum(s, dut, 0, 7)


@cocotb.test()
async def with_positive(dut):
    s = await setup(dut)
    await check_sum(s, dut, 10, 10)


@cocotb.test()
async def with_negative(dut):
    s = await setup(dut)
    await check_sum(s, dut, -8, 7)
    await check_sum(s, dut, -8, -7)


@cocotb.test()
async def extremes(dut):
    s = await setup(dut)
    for a, b in [
        (INT32_MAX, INT32_MAX),
        (INT32_MIN, INT32_MIN),
        (INT32_MIN, INT32_MAX),
    ]:
        await check_sum(s, dut, a, b)


@cocotb.test()
async def random_values(dut):
    s = await setup(dut)
    for _ in range(100):
        a = random.randint(INT32_MIN, INT32_MAX)
        b = random.randint(INT32_MIN, INT32_MAX)
        await check_sum(s, dut, a, b)
