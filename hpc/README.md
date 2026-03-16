# gromacs_status.sh

A terminal-based status explorer for GROMACS molecular dynamics simulations managed with SLURM. It scans a directory tree, identifies all active simulation directories by their output files, queries `squeue` for live job state, parses GROMACS and MPI error blocks, and prints a colour-coded summary table.

---

## Features

- **No directory name assumptions** — discovery is fingerprint-based (`.tpr`, `.cpt`, `.edr`, `.xtc`, `.log`). Works with any folder layout.
- **SLURM-authoritative status** — calls `squeue` once at startup. Running and pending (queued) jobs override file-based heuristics.
- **Name-based job matching** — PD (pending) jobs that haven't created `.err` files yet are matched to their directory by extracting replica and system numbers from both the path and the job name.
- **Three-layer error parsing** — GROMACS fatal block (from `.out`), MPI/prterun messages (from `.err`), and generic SLURM errors shown inline under each failed row.
- **Timestep-aware time display** — step counts are multiplied by `dt` (configurable) and auto-scaled to ps / ns / µs.
- **Log rotation** — always saves a timestamped log; keeps the 10 most recent automatically.

---

## Requirements

| Tool | Notes |
|---|---|
| `bash` ≥ 4.2 | Associative arrays required |
| `gawk` / `awk` | Standard on all HPC systems |
| `grep` with `-P` | Perl-compatible regex (GNU grep) |
| `squeue` | Optional — needed for live SLURM state |
| `du` | Optional — needed for disk usage column |
| `timeout` | Optional — protects `du` on slow filesystems |

---

## Installation

```bash
# Copy to your project directory or somewhere on your PATH
cp gromacs_status.sh ~/bin/
chmod +x ~/bin/gromacs_status.sh
```

---

## Quick Start

```bash
# Run from the directory that contains your simulation folders
./gromacs_status.sh .

# Or point to a specific root
./gromacs_status.sh /scratch/user/project
```

On the first run (without `-p`) the script will ask two interactive questions:

```
Step 1 — Output file pattern
  Detected candidates:
    [1] 9.production
    [2] 7.equilibration

  Pattern [e.g. 9.production]: 1

Step 2 — SLURM log prefix
  Default: MD_SIMULATION  →  MD_SIMULATION.err.<jobid>
  SLURM prefix [Enter = keep 'MD_SIMULATION']:
```

Selecting a pattern (e.g. `9.production`) tells the script to look for `9.production.log`, `9.production.xtc`, `9.production.cpt`, etc., so it reads the right files in every replica directory.

---

## Usage

```
./gromacs_status.sh [ROOT_DIR] [OPTIONS]
```

### Options

| Flag | Default | Description |
|---|---|---|
| `-p, --pattern NAME` | _(interactive)_ | Base name of GROMACS output files, e.g. `9.production` |
| `--slurm-prefix PFX` | `MD_SIMULATION` | Prefix of SLURM log files → `PFX.err.<jobid>` |
| `-d, --depth N` | unlimited | Maximum directory search depth |
| `-e, --errors-only` | off | Show only FAILED / INCOMPLETE / QUEUED rows |
| `-v, --verbose` | off | Show file inventory below each row |
| `-x, --exclude PATTERN` | _(none)_ | Skip directories whose path contains `PATTERN`. Repeatable. |
| `--no-color` | off | Disable ANSI colours (good for piping or `grep`) |
| `--no-gromacs-err` | on | Do not parse the GROMACS fatal error block |
| `--no-mpi-err` | on | Do not parse MPI/prterun error lines |
| `--no-slurm-out` | on | Do not read `.out` file for progress/error info |
| `--no-disk` | on | Skip `du -sh` per directory (faster on slow filesystems) |
| `--time-unit UNIT` | auto | Force time display unit: `ps`, `ns`, or `us` |
| `--dt VAL` | `0.02` | Integration timestep in ps. Default = 20 fs (MARTINI CG). Use `0.002` for atomistic (2 fs). |
| `--err-lines N` | `3` | Lines of inline error context per error type. `0` = label only. |
| `-l, --log [DIR]` | `./md_status_logs` | Save output to a timestamped log file. Last 10 logs are kept. |
| `-h, --help` | — | Print help and exit |

---

## Examples

```bash
# Minimal — interactive prompts for pattern and SLURM prefix
./gromacs_status.sh .

# Fully non-interactive — production run with all flags set
./gromacs_status.sh /scratch/proj \
    -p 9.production \
    --slurm-prefix MD_SIMULATION \
    --dt 0.02 \
    --time-unit us

# Show only problems (failed, incomplete, queued)
./gromacs_status.sh . -p 9.production -e

# Atomistic run with 2 fs timestep, time in ns
./gromacs_status.sh /scratch/atomistic -p md_production --dt 0.002 --time-unit ns

# More error context (5 lines per error type)
./gromacs_status.sh . -p 9.production --err-lines 5

# Skip disk usage (faster on Panasas / Lustre / GPFS)
./gromacs_status.sh . -p 9.production --no-disk

# Exclude backup and test directories
./gromacs_status.sh . -p 9.production -x backup -x test -x old

# Limit search depth to 4 levels
./gromacs_status.sh /large/project -p 9.production -d 4

# Save log to a custom directory, disable colour for grep
./gromacs_status.sh . -p 9.production --no-color -l /home/user/sim_logs

# Verbose file inventory + errors only
./gromacs_status.sh . -p 9.production -e -v
```

---

## Output

### Table columns

| Column | Description |
|---|---|
| `PATH (relative)` | Directory path relative to the root |
| `STATUS` | Simulation state (see below) |
| `JOB ID` | SLURM job ID from the latest `.err` file or squeue |
| `SIM TIME` | Simulated time (steps × dt), auto-scaled |
| `STEPS` | Last step number reached |
| `DISK` | Directory size from `du -sh` |
| `ATOMS` | Atom count parsed from the GROMACS log |
| `FILES` | Presence of key output files (● = present, ○ = absent) |

### Status values

| Status | Colour | Meaning |
|---|---|---|
| `FINISHED ✔` | Green | `confout.gro` present **and** `Finished mdrun` in log |
| `RUNNING ▶` | Cyan | Job is `R` in `squeue`, or `.cpt` modified within the last 60 min |
| `QUEUED ⏳` | Blue | Job is `PD` (pending) in `squeue` — matched by job name or `.err` file |
| `INCOMPLETE ⚠` | Yellow | `.cpt` or `.edr` found but no clean finish and no error detected |
| `FAILED ✖` | Red | Error pattern found in SLURM `.err` or `.out` files |
| `NOT_STARTED ○` | Dim | `.tpr` found but no output files yet |
| `NO_TPR ✗` | Magenta | No `.tpr` found — may not be a simulation directory |

### Error sub-rows (under FAILED rows)

```
  14.2/.../replica2  FAILED ✖   1624873   ...
    ├ GROMACS  File input/output error:
    ├ GROMACS  Cannot rename checkpoint file; maybe you are out of disk space?
    ├ MPI/PAR  MPI_ABORT was invoked on rank 0 in communicator MPI_COMM_WORLD
    ├ MPI/PAR  prterun has exited due to process rank 0 with PID 0 on node ...
    └ OTHER    sbatch: error: Batch script is empty!
```

| Label | Colour | Source |
|---|---|---|
| `GROMACS` | Red | The `-------` fatal error block in the GROMACS `.out` file |
| `MPI/PAR` | Orange | `MPI_ABORT`, `prterun`, segfault, OOM from the `.err` file |
| `OTHER` | Yellow | `sbatch` errors, missing files, I/O errors |

### Performance sub-row (under FINISHED rows)

```
  14.1/.../replica1  FINISHED ✔   ...
    └ PERF   ns/day: 2.345   hours/ns: 10.234   wall time: 34h12m07s
```

### Progress sub-row (under RUNNING / INCOMPLETE rows)

```
  14.1/.../replica2  RUNNING ▶   ...
    └ PROGRS  imb F 18% step 137931100, will finish Wed Mar 18 14:26:06 2026
```

---

## Log Files

Every run saves a timestamped log to `./md_status_logs/` (or the directory set with `-l`):

```
md_status_logs/
  md_status_20260316_143201.log   ← terminal output (with ANSI stripped)
  md_status_20260316_091045.log
  ...                             (10 most recent kept automatically)
```

The log contains everything printed to the terminal **plus** a `FAILED SIMULATIONS — FULL DETAIL` section that is not shown on screen. This section includes the complete content of each SLURM `.err` file for every failed simulation.

---

## How SLURM State Is Determined

The script calls `squeue -u $USER` once at startup and builds an in-memory lookup table. For each simulation directory it tries two matching strategies in order:

1. **Exact match** — scans `.err` files in the directory, extracts their job IDs, and looks each one up in the squeue table. Works for jobs that are running or recently started.

2. **Name match** — for pending (`PD`) jobs that have not yet created a `.err` file, extracts the replica number and system number from the directory path and matches them against squeue job names. For example, directory `CCPG1-2SIGMAR1/replica3` will match a job named `r3_..._sigmar1-2_...`.

If `squeue` is not available, the script falls back to file-based heuristics (checkpoint modification time, presence of output files).

---

## Notes on Specific Setups

### MARTINI Coarse-Grained (default)
The default `--dt 0.02` (20 fs) is correct for standard MARTINI runs with a 20 fs timestep.

### Atomistic simulations
Use `--dt 0.002` (2 fs) for standard atomistic AMBER/CHARMM/OPLS runs:
```bash
./gromacs_status.sh . -p md_production --dt 0.002 --time-unit ns
```

### Slow network filesystems (Panasas, Lustre, GPFS)
The `du -sh` call is wrapped with `timeout 15`. If your filesystem is slow enough to cause timeouts (showing `?` in the DISK column), disable disk reporting entirely:
```bash
./gromacs_status.sh . -p 9.production --no-disk
```

### Custom SLURM log naming
If your cluster uses a different prefix (e.g. `run.err.1234567` instead of `MD_SIMULATION.err.1234567`):
```bash
./gromacs_status.sh . -p 9.production --slurm-prefix run
```
