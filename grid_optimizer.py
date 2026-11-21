#!/usr/bin/env python3
"""
Campus Microgrid Controller - WEC Fall 2026 (Programming)

Connects to the simulator at localhost:8800. Each simulated hour it receives the
campus state (random event, weather forecast, building loads, grid price) and
replies with how much solar / battery / grid energy each building gets, plus how
much the backup generator should produce to recharge the shared battery.

Strategy (cost-minimising, priority based):
  1. Solar ($0) goes to every building that can take it (not lecture halls).
  2. Stored battery energy goes first to lecture halls (they cannot use solar),
     and is only spent when it saves money: grid price above the generator cost,
     a grid failure, or energy that would otherwise be left over at the end of
     the day.
  3. The grid covers whatever is left.
  4. The generator ($1/unit) keeps the battery full as grid-failure insurance.
     When the grid costs more than $1, the battery is spent and immediately
     refilled, so every stored unit displaces more expensive grid power.
"""

import json
import socket
import sys

# ----------------------------------------------------------------- constants
HOST, PORT = "localhost", 8800

HOURS_PER_DAY = 24
SOLAR_CAPACITY = 200.0          # units per hour, $0
GENERATOR_COST = 1.00           # $ per unit
BATTERY_CAPACITY = 100.0        # charging past this errors
INITIAL_BATTERY = 0.0           # spec doesn't say; assume empty

# Spec-ambiguity switches (confirm with organizers)
GENERATOR_ENERGY_SAME_HOUR = False  # can generator output be discharged the same hour?
NO_SOLAR_FOLLOWS_FORECAST = False   # treat last hour's "cloudy" forecast as no solar now?

NO_SOLAR_TYPES = {"lecture_hall"}
SOURCES = ("solar", "battery", "grid")
EPS = 1e-9


# ----------------------------------------------------------------- controller
class MicrogridController:
    """Keeps state across hours and makes one allocation decision per hour."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.hour = 0
        self.battery = INITIAL_BATTERY
        self.last_forecast = "not cloudy"

    # -------------------------------------------------- helpers
    def hours_left(self):
        """Hours remaining after the current one."""
        return HOURS_PER_DAY - self.hour - 1

    # -------------------------------------------------- main decision
    def decide(self, msg):
        event = msg.get("random_event", "none")
        loads = [{"type": l["type"], "load": float(l["load"])} for l in msg["loads"]]
        price = float(msg.get("grid_price", GENERATOR_COST))

        solar_ok = event != "cloudy_weather"
        if NO_SOLAR_FOLLOWS_FORECAST and self.last_forecast == "cloudy":
            solar_ok = False
        battery_ok = event != "battery_failure"
        grid_ok = event != "grid_failure"
        generator_ok = event != "generator_failure" and battery_ok

        # Keep the battery full as grid-failure insurance: an unmet building is far
        # worse than $1/unit, and leftover charge is spent in the final hour anyway.
        reserve = BATTERY_CAPACITY

        # How much battery energy are we willing to spend this hour?
        stored = self.battery if battery_ok else 0.0
        if not grid_ok or self.hours_left() == 0:
            budget = stored                          # emergency / last hour: use it all
        elif price > GENERATOR_COST and generator_ok:
            budget = stored                          # spend now, generator refills the reserve
        elif price > GENERATOR_COST:
            budget = max(0.0, stored - reserve)      # can't refill: keep the reserve
        else:
            budget = 0.0                             # grid is cheaper than refilling

        alloc, unmet = self.allocate(loads, solar_ok, budget, grid_ok)
        if unmet > EPS:
            print(f"[warn] hour {self.hour}: {unmet:.2f} units unmet ({event})",
                  file=sys.stderr)

        used_battery = sum(a["battery"] for a in alloc)
        self.battery -= used_battery

        generator = self.plan_generator(generator_ok, reserve) if generator_ok else 0.0
        self.battery += generator

        self.last_forecast = msg.get("forecast", "not cloudy")
        self.hour += 1
        if self.hour >= HOURS_PER_DAY:
            self.reset()

        return {"buildings": [clean(a) for a in alloc], "generator": num(generator)}

    @staticmethod
    def allocate(loads, solar_ok, battery_budget, grid_ok):
        """Fill each building's load cheapest-first. Returns (allocations, unmet)."""
        remaining = [l["load"] for l in loads]
        alloc = [{s: 0.0 for s in SOURCES} for _ in loads]

        def give(source, pool, indices):
            for i in indices:
                take = min(remaining[i], pool)
                alloc[i][source] += take
                remaining[i] -= take
                pool -= take
            return pool

        solar_ready = [i for i, l in enumerate(loads) if l["type"] not in NO_SOLAR_TYPES]
        no_solar = [i for i, l in enumerate(loads) if l["type"] in NO_SOLAR_TYPES]

        # 1. Free solar wherever allowed
        if solar_ok:
            give("solar", SOLAR_CAPACITY, solar_ready)

        # 2. Battery: lecture halls first, since only battery/grid can power them
        give("battery", battery_budget, no_solar + solar_ready)

        # 3. Grid for the rest
        if grid_ok:
            give("grid", float("inf"), range(len(loads)))

        return alloc, sum(remaining)

    def plan_generator(self, generator_ok, reserve):
        """Decide how much to generate into the battery this hour."""
        if not generator_ok:
            return 0.0
        # Energy made now can be used next hour at the earliest (unless switched).
        usable_hours = self.hours_left() + (1 if GENERATOR_ENERGY_SAME_HOUR else 0)
        if usable_hours <= 0:
            return 0.0

        target = min(reserve, BATTERY_CAPACITY)
        return max(0.0, target - self.battery)


# ----------------------------------------------------------------- formatting
def num(x):
    """Round floating noise; send whole numbers as ints."""
    x = round(x, 6)
    return int(x) if x == int(x) else x


def clean(a):
    return {s: num(a[s]) for s in SOURCES}


# ----------------------------------------------------------------- networking
def messages(sock):
    """Yield JSON objects from the socket, whatever the framing."""
    decoder = json.JSONDecoder()
    buf = ""
    while True:
        chunk = sock.recv(65536)
        if not chunk:
            return
        buf += chunk.decode()
        while True:
            buf = buf.lstrip()
            if not buf:
                break
            try:
                obj, end = decoder.raw_decode(buf)
            except json.JSONDecodeError:
                break                       # wait for the rest of the message
            buf = buf[end:]
            yield obj


def main():
    controller = MicrogridController()
    with socket.create_connection((HOST, PORT)) as sock:
        for msg in messages(sock):
            if not isinstance(msg, dict) or "loads" not in msg:
                continue                    # ignore non-state messages (e.g. scores)
            reply = controller.decide(msg)
            sock.sendall((json.dumps(reply) + "\n").encode())


if __name__ == "__main__":
    main()
