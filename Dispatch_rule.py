# Dispatch rule for the AFIT satellite range scheduling problem: earliest end time first.
#
#   1. Order the operations in ascending order of end time, e_i.
#   2. Pick the first operation, o, and schedule it.
#   3. Remove o and all the operations that overlap with o from the list.
#   4. If the list is empty, you are done. If not, go to step 2.
#
# In this problem:
#   - an operation is one (request r, antenna a) pair, i.e. one row of the data file
#   - each operation has fixed times at its earliest start: turnaround then task, [S - Q, S + P)
#   - its end time is e = S + P
#   - an operation overlaps o if it is on the same antenna and its interval intersects o's,
#     or if it belongs to the same request (each request is scheduled at most once)

## Imports
import os, platform, time
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


def eet_dispatch(opts):
    '''
    Earliest end time first. Returns assign {r: (a, start)}.
    Operations are visited in end-time order, so an operation overlaps something already scheduled
    on antenna a exactly when it starts before the end of the last operation scheduled on a.
    Skipping those operations is the same as removing them from the list in step 3.
    '''
    # step 1: all operations, fixed at their earliest start, sorted by end time (ties: earlier start)
    ops = sorted((lo + L, lo, r, a) for r in range(len(opts)) for (a, lo, hi, L) in opts[r])

    assign = {}    # r -> (a, start)
    last_end = {}  # a -> end time of the last operation scheduled on antenna a
    for e, s, r, a in ops:                          # step 2: next operation in the list
        if r in assign:                             # step 3: removed, request already scheduled
            continue
        if s < last_end.get(a, float("-inf")):      # step 3: removed, overlaps an operation on antenna a
            continue
        assign[r] = (a, s)                          # schedule it
        last_end[a] = e
    return assign                                   # step 4: list exhausted


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
    Takes in a problem instance, schedules it with the earliest-end-time dispatch rule,
    and returns the solution, run info, and machine info.
    '''
    start_time = time.time()

    # getting data
    data = read_instance(problem_data, combine_data)
    opts, opt_of = build_options(data)

    # dispatch rule
    assign = eet_dispatch(opts)
    verify(assign, opt_of)

    info = {
        "Rule": "EarliestEndTime",
        "Objective": len(assign),
        "NumberOfRequests": len(data["R"]),
        "NumberOfOperations": sum(len(o) for o in opts),
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
