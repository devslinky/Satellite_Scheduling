# Dispatch rule for the AFIT satellite range scheduling problem: Earliest Deadline First (EDF)
# with earliest-feasible insertion (report Section 3, Algorithm 1).
#
#   1. Sort requests by deadline E_ra ascending; break ties by the shorter window E_ra - S_ra,
#      then by request ID.
#   2. For each request in that order, on each candidate antenna (increasing index), find the
#      earliest start t >= S_ra - Q_ra such that the block [t, t + P_ra + Q_ra) fits in an idle
#      gap of that antenna and t + P_ra + Q_ra <= E_ra.
#   3. Assign the request to the antenna with the smallest t (ties: lowest antenna index),
#      or leave it unscheduled if no antenna has a feasible t. A request is never moved
#      after it has been placed.
#
# Since E_ra and S_ra can differ by antenna (day 12), a request's deadline is its earliest
# E_ra over its candidate antennas, and its window length is its shortest E_ra - S_ra.

## Imports
import os, platform, time, bisect
import psutil
from Instance_reader import *


def build_options(data):
    '''
    Returns:
      opts[r]   = list of (a, lo, hi, L) for request r
      opt_of[r] = {a: (lo, hi, L)} for fast lookup
    where lo/hi are the earliest/latest start of the interval (turnaround included) and L = P + Q.
    '''
    S_ra, E_ra, P_ra, Q_ra, A_r = data["S_ra"], data["E_ra"], data["P_ra"], data["Q_ra"], data["A_r"]
    opts, opt_of = [], []
    for r in range(len(data["R"])):
        r_opts = []
        for a in A_r[r]:
            lo = S_ra[r][a] - Q_ra[r][a]
            hi = E_ra[r][a] - P_ra[r][a] - Q_ra[r][a]
            L = P_ra[r][a] + Q_ra[r][a]
            if lo <= hi:  # skip pairs that can never fit in their window
                r_opts.append((a, lo, hi, L))
        opts.append(r_opts)
        opt_of.append({a: (lo, hi, L) for (a, lo, hi, L) in r_opts})
    return opts, opt_of


def edf_order(data):
    '''Algorithm 1, line 1: requests sorted by deadline, then shorter window, then request ID.'''
    S_ra, E_ra, A_r = data["S_ra"], data["E_ra"], data["A_r"]
    def key(r):
        deadline = min(E_ra[r][a] for a in A_r[r])
        window = min(E_ra[r][a] - S_ra[r][a] for a in A_r[r])
        return (deadline, window, r)
    return sorted(range(len(data["R"])), key=key)


def earliest_fit(schedule, lo, hi, L):
    '''
    Algorithm 1, line 7: earliest start t >= lo such that [t, t + L) is disjoint from every block in
    schedule (a list of (start, end) sorted by start). Returns None if t would exceed hi = E - P - Q,
    i.e. the block would end after the window closes (line 8).
    '''
    prev_end = float("-inf")
    for (s, e) in schedule:
        if e <= lo:  # block ends before we could start; only its end matters
            prev_end = e
            continue
        t = max(lo, prev_end)
        if t > hi:
            return None
        if t + L <= s:  # fits in the idle gap before this block
            return t
        prev_end = e
    t = max(lo, prev_end)
    return t if t <= hi else None


def edf_dispatch(order, opts, n_antennas):
    '''Algorithm 1, lines 2-14. Returns assign {r: (a, start)} and the unscheduled requests U.'''
    sched = [[] for _ in range(n_antennas)]  # occupied blocks per antenna
    assign, U = {}, []
    for r in order:
        best = None  # (t*, a*)
        for (a, lo, hi, L) in sorted(opts[r]):  # candidate antennas in increasing index
            t = earliest_fit(sched[a], lo, hi, L)
            if t is not None and (best is None or t < best[0]):  # strict <: ties keep the lowest index
                best = (t, a, L)
        if best is not None:
            t, a, L = best
            bisect.insort(sched[a], (t, t + L))  # contact starts at t + Q_ra
            assign[r] = (a, t)
        else:
            U.append(r)
    return assign, U


def verify(assign, opt_of):
    '''Asserts every operation is inside its window, no overlap per antenna, one placement per request.'''
    timelines = {}
    for r, (a, s) in assign.items():
        lo, hi, L = opt_of[r][a]
        assert lo <= s <= hi, f"request {r} on antenna {a} outside its window"
        timelines.setdefault(a, []).append((s, s + L, r))
    for a, tl in timelines.items():
        tl.sort()
        for prev, cur in zip(tl, tl[1:]):
            assert prev[1] <= cur[0], f"overlap on antenna {a} between requests {prev[2]} and {cur[2]}"


def dispatch_heuristic(problem_data:str, write_results_to_file:bool = False, combine_data:bool = False):
    '''
    Takes in a problem instance, schedules it with the EDF dispatch rule (Algorithm 1),
    and returns the solution, run info, and machine info.
    '''
    start_time = time.time()

    # getting data
    data = read_instance(problem_data, combine_data)
    opts, opt_of = build_options(data)

    # dispatch rule
    assign, U = edf_dispatch(edf_order(data), opts, len(data["A"]))
    verify(assign, opt_of)

    info = {
        "Rule": "EarliestDeadlineFirst",
        "Objective": len(assign),
        "NumberOfRequests": len(data["R"]),
        "Unscheduled": len(U),
        "NumberOfRequestAntennaPairs": sum(len(o) for o in opts),
        "SolveTime": round(time.time() - start_time, 3),
    }

    # getting machine solving context
    processor = str(platform.processor())
    cores = str(os.cpu_count())
    memory = str(psutil.virtual_memory().total)

    if write_results_to_file:
        write_dispatch_results(assign, info, processor, cores, memory, problem_data, data, opt_of)

    return (assign, info, processor, cores, memory, problem_data)


def write_dispatch_results(assign, info, processor, cores, memory, problem_data, data, opt_of):
    # write results to file, in the same layout as CP_model.write_results
    R, A = data["R"], data["A"]
    with open(f"results/dispatch_{problem_data}.txt", "w") as f:
        for k, v in info.items():
            f.write(f"{k}: {v}\n")
        f.write(f"Processor: {processor}\n")
        f.write(f"Cores: {cores}\n")
        f.write(f"Memory: {memory}\n")
        f.write("\n\n")
        f.write(f"Solution Objective value: ({info['Objective']},)\n")
        f.write("\n\n")

        for r in range(len(R)):
            for a in data["A_r"][r]:
                f.write(f" variable name: I_{R[r]}_{A[a]}")
                if r in assign and assign[r][0] == a:
                    t = assign[r][1]
                    f.write(f" variable start: {t}")
                    f.write(f" variable end: {t + opt_of[r][a][2]}")
                f.write("\n\n")


if __name__ == "__main__":
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else "12"
    _, info, *_ = dispatch_heuristic(day, write_results_to_file=False, combine_data=True)
    for k, v in info.items():
        print(f"{k}: {v}")
