# top = mul16::mul16

import random

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge
from spade import SpadeExt

INT16_MIN = -(2**15)
INT16_MAX = 2**15 - 1


def wrap16(x):
    return (x - INT16_MIN) % 2**16 + INT16_MIN


async def setup(dut):
    s = SpadeExt(dut)
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    await FallingEdge(dut.clk_i)
    return s


async def check_product(s, dut, a, b):
    s.i.a, s.i.b = str(a), str(b)
    await FallingEdge(dut.clk_i)
    s.o.product.assert_eq(str(wrap16(a * b)))


@cocotb.test()
async def zero(dut):
    s = await setup(dut)
    await check_product(s, dut, 0, 12345)


@cocotb.test()
async def with_positive(dut):
    s = await setup(dut)
    await check_product(s, dut, 6, 7)


@cocotb.test()
async def with_negative(dut):
    s = await setup(dut)
    await check_product(s, dut, -8, 7)
    await check_product(s, dut, -8, -7)


@cocotb.test()
async def extremes(dut):
    s = await setup(dut)
    for a, b in [
        (INT16_MAX, INT16_MAX),
        (INT16_MIN, INT16_MIN),
        (INT16_MIN, INT16_MAX),
        (INT16_MIN, -1),
        (256, 256),
    ]:
        await check_product(s, dut, a, b)


@cocotb.test()
async def random_values(dut):
    s = await setup(dut)
    for _ in range(100):
        a = random.randint(INT16_MIN, INT16_MAX)
        b = random.randint(INT16_MIN, INT16_MAX)
        await check_product(s, dut, a, b)
