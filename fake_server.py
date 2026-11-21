#!/usr/bin/env python3
"""
Local stand-in for the WEC simulator (for testing only - NOT part of the submission).
Runs one 24-hour day on localhost:8800, validates replies and prints the total cost.
Usage: python3 fake_server.py [seed]   then, in another terminal: python3 main.py
"""
import json
import random
import socket
import sys

SOLAR_CAP, GEN_COST, BAT_CAP = 200, 1.0, 100
TYPES = ["library", "laboratory", "lecture_hall", "student_centre", "student_residence"]
EVENTS = ["none"] * 8 + ["cloudy_weather", "generator_failure", "battery_failure", "grid_failure"]


def main():
    rng = random.Random(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("localhost", 8800))
    srv.listen(1)
    conn, _ = srv.accept()
    f = conn.makefile("r")
    battery, cost, errors = 0.0, 0.0, 0
    for hour in range(24):
        event = rng.choice(EVENTS)
        loads = [{"type": t, "load": rng.randint(10, 80)} for t in TYPES]
        price = round(rng.uniform(0.4, 1.8), 2)
        msg = {"random_event": event, "forecast": rng.choice(["cloudy", "not cloudy"]),
               "loads": loads, "grid_price": price}
        conn.sendall((json.dumps(msg) + "\n").encode())
        reply = json.loads(f.readline())

        b = reply["buildings"]
        solar = sum(x["solar"] for x in b)
        bat = sum(x["battery"] for x in b)
        grid = sum(x["grid"] for x in b)
        gen = reply["generator"]
        problems = []
        for l, x in zip(loads, b):
            if abs(x["solar"] + x["battery"] + x["grid"] - l["load"]) > 1e-6:
                problems.append(f"{l['type']} demand not met")
            if l["type"] == "lecture_hall" and x["solar"] > 0:
                problems.append("solar to lecture hall")
        if solar > SOLAR_CAP + 1e-6: problems.append("solar over cap")
        if event == "cloudy_weather" and solar > 0: problems.append("solar while cloudy")
        if event == "grid_failure" and grid > 0: problems.append("grid while failed")
        if event == "battery_failure" and (bat > 0 or gen > 0): problems.append("battery while failed")
        if event == "generator_failure" and gen > 0: problems.append("generator while failed")
        if bat > battery + 1e-6: problems.append("battery overdrawn")
        battery -= bat
        if battery + gen > BAT_CAP + 1e-6: problems.append("battery overcharged")
        battery += gen
        hour_cost = grid * price + gen * GEN_COST
        cost += hour_cost
        errors += bool(problems)
        print(f"h{hour:02d} {event:17s} price {price:.2f}  solar {solar:5.0f} bat {bat:5.0f} "
              f"grid {grid:5.0f} gen {gen:5.0f} | stored {battery:5.1f} | ${hour_cost:7.2f}"
              + (f"  !! {problems}" if problems else ""))
    print(f"TOTAL COST ${cost:.2f}   hours with errors: {errors}")
    conn.close()


if __name__ == "__main__":
    main()
