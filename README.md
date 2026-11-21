# Campus Microgrid Controller — WEC Fall 2026 (Programming)

An automated controller for the University of Waterloo campus microgrid. Every simulated hour it receives building loads, the grid price, random events, and a weather forecast from the simulator (socket `localhost:8800`). It replies with how much solar, battery and grid energy each building gets and how much the backup generator should produce, while keeping the total operating cost over 24 hours as low as possible.

## Running

```bash
python3 main.py              # simulator must already be listening on localhost:8800
```

Local testing without the official simulator:

```bash
python3 fake_server.py 42    # terminal 1 (seed optional)
python3 main.py              # terminal 2
```

## Strategy

1. **Solar first.** It's free and capped at 200 units/hour. It goes to every building except lecture halls, which can't take solar.
2. **Battery next, lecture halls first,** since they can only use the battery or the grid. The battery is spent only when that saves money:
   - the grid price is above the generator's $1/unit,
   - the grid has failed, or
   - it's the final hour and any leftover charge would be wasted.
3. **The grid covers the rest.**
4. **The generator keeps the battery full** as grid-failure insurance. When the grid costs more than $1, the battery is spent and refilled in the same hour, saving `(price − $1)` on every unit.

Random events (`cloudy_weather`, `generator_failure`, `battery_failure`, `grid_failure`) disable the matching source for that hour.

## Files

| File | Purpose |
|---|---|
| `grid_optimizer.py` | Controller logic and socket client |
| `main.py` | Entry point (runs `grid_optimizer.main`) |
| `fake_server.py` | Local simulator stand-in: validates replies and reports total cost (not submitted) |
