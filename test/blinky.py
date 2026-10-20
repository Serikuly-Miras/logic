# top = blinky::blinky_test

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, FallingEdge
from spade import SpadeExt

DURATION = 100


async def setup(dut):
    s = SpadeExt(dut)
    await cocotb.start(Clock(dut.clk_i, period=10, units="ns").start())
    await FallingEdge(dut.clk_i)
    return s


async def reset(s, dut):
    s.i.rst = "true"
    await FallingEdge(dut.clk_i)
    s.o.assert_eq("false")
    s.i.rst = "false"


@cocotb.test()
async def off_after_quarter(dut):
    s = await setup(dut)
    await reset(s, dut)
    await ClockCycles(dut.clk_i, DURATION // 4, rising=False)
    s.o.assert_eq("false")


@cocotb.test()
async def on_after_three_quarters(dut):
    s = await setup(dut)
    await reset(s, dut)
    await ClockCycles(dut.clk_i, DURATION * 3 // 4, rising=False)
    s.o.assert_eq("true")
