# Dispatch-rule heuristic for the AFIT satellite range scheduling problem.
#
# Same instance and rules as CP_model.py:
#   - for each feasible (request r, antenna a) pair, a task occupies [t, t + P + Q) on antenna a
#     (turnaround Q first, then the task P), with t in [S - Q, E - P - Q]
#   - tasks on the same antenna cannot overlap
#   - each request is scheduled on at most one antenna
#   - objective: maximize the number of scheduled requests
#
# Algorithm:
#   1. Priority rule: sort requests by (least slack, fewest candidate antennas, earliest deadline)
#   2. Constructive dispatch: place each request at its earliest feasible start, on the antenna
#      where it finishes earliest
#   3. Improvement: insert unscheduled requests by shifting tasks within their windows
#      (shift-insert), or by moving one blocking task elsewhere (eject-and-relocate)
#   4. Randomized restarts: perturb the priority order, keep the best solution
#   Terminating conditions: time limit, iteration limit, iterations without improvement,
#   or reaching an upper bound on the objective.

## Imports
import os, platform, time, random, bisect
import psutil
from Instance_reader import *

NEG_INF = float("-inf")


def build_options(data):
    '''
    Returns:
      opts[r]   = list of (a, lo, hi, L) placement options for request r
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


def priority_keys(data):
    '''
    Dispatch rule key per request: (slack, number of candidate antennas, deadline).
    slack = max over antennas of (E - S - P), deadline = min over antennas of E.
    '''
    S_ra, E_ra, P_ra, A_r = data["S_ra"], data["E_ra"], data["P_ra"], data["A_r"]
    keys = []
    for r in range(len(data["R"])):
        slack = max(E_ra[r][a] - S_ra[r][a] - P_ra[r][a] for a in A_r[r])
        deadline = min(E_ra[r][a] for a in A_r[r])
        keys.append((slack, len(A_r[r]), deadline))
    return keys


def priority_order(keys, rng=None, swap_frac=0.05):
    '''
    Deterministic order when rng is None. Otherwise the slack is jittered (x0.7-1.3), ties are
    broken randomly, and a few random adjacent swaps are applied.
    '''
    n = len(keys)
    if rng is None:
        return sorted(range(n), key=lambda r: (keys[r], r))

    order = sorted(range(n), key=lambda r: (keys[r][0] * rng.uniform(0.7, 1.3), keys[r][1], keys[r][2], rng.random()))
    for _ in range(int(swap_frac * n)):
        i = rng.randrange(n - 1)
        order[i], order[i + 1] = order[i + 1], order[i]
    return order


def earliest_fit(timeline, lo, hi, L):
    '''
    timeline: list of (start, end, r) sorted by start, non-overlapping.
    Returns the earliest start t in [lo, hi] such that [t, t+L) fits in a gap, or None.
    '''
    prev_end = NEG_INF
    for (s, e, _) in timeline:
        if e <= lo:  # task ends before we could start; only its end matters
            prev_end = e
            continue
        t = max(lo, prev_end)
        if t > hi:
            return None
        if t + L <= s:
            return t
        prev_end = e
    t = max(lo, prev_end)
    return t if t <= hi else None


def construct(order, opts, n_antennas):
    '''
    Greedy dispatch: for each request in order, choose the antenna with the earliest finish time
    (ties: fewer tasks on the antenna), placed at its earliest feasible start.
    Returns assign {r: (a, t)} and timelines[a] = sorted list of (start, end, r).
    '''
    assign = {}
    timelines = [[] for _ in range(n_antennas)]
    for r in order:
        best = None
        for (a, lo, hi, L) in opts[r]:
            t = earliest_fit(timelines[a], lo, hi, L)
            if t is not None:
                key = (t + L, len(timelines[a]))
                if best is None or key < best[0]:
                    best = (key, a, t, L)
        if best is not None:
            _, a, t, L = best
            bisect.insort(timelines[a], (t, t + L, r))
            assign[r] = (a, t)
    return assign, timelines


def forward_pass(seq, a, opt_of):
    '''
    seq: list of requests in the order they run on antenna a.
    Left-justifies the sequence: t_i = max(lo_i, end_{i-1}). Returns the timeline, or None if any
    task would start after its latest start hi_i.
    '''
    new = []
    prev_end = NEG_INF
    for r in seq:
        lo, hi, L = opt_of[r][a]
        t = max(lo, prev_end)
        if t > hi:
            return None
        new.append((t, t + L, r))
        prev_end = t + L
    return new


def try_shift_insert(timeline, a, u, opt_of):
    '''
    Tries to insert request u into antenna a's sequence, re-timing the tasks within their windows.
    Only insertion positions near u's window are tried. Returns the new timeline or None.
    No side effects.
    '''
    lo, hi, L = opt_of[u][a]
    seq = [r for (_, _, r) in timeline]
    n = len(seq)
    k_min = 0
    while k_min < n and timeline[k_min][1] <= lo:  # tasks ending before u can start stay ahead of u
        k_min += 1
    k_max = k_min
    while k_max < n and timeline[k_max][0] < hi + L:  # tasks starting after u's latest end stay behind u
        k_max += 1
    for k in range(k_min, k_max + 1):
        new = forward_pass(seq[:k] + [u] + seq[k:], a, opt_of)
        if new is not None:
            return new
    return None


def set_timeline(a, new, timelines, assign):
    timelines[a] = new
    for (t, _, r) in new:
        assign[r] = (a, t)


def insert_anywhere(u, opts, opt_of, timelines, assign):
    '''Shift-inserts u on the first candidate antenna where it fits. Returns True on success.'''
    for (a, _, _, _) in opts[u]:
        new = try_shift_insert(timelines[a], a, u, opt_of)
        if new is not None:
            set_timeline(a, new, timelines, assign)
            return True
    return False


def eject_and_relocate(u, opts, opt_of, timelines, assign):
    '''
    For each candidate antenna a of u and each task v on a that overlaps u's possible span:
    remove v, shift-insert u on a, then shift-insert v anywhere. Net gain +1 if both succeed.
    Rolls back otherwise. Returns True on success.
    '''
    for (a, lo, hi, L) in opts[u]:
        old = timelines[a]
        for (s, e, v) in old:
            if e <= lo or s >= hi + L:
                continue
            without_v = [task for task in old if task[2] != v]
            new_a = try_shift_insert(without_v, a, u, opt_of)
            if new_a is None:
                continue
            del assign[v]
            set_timeline(a, new_a, timelines, assign)
            if insert_anywhere(v, opts, opt_of, timelines, assign):
                return True
            # roll back
            del assign[u]
            set_timeline(a, old, timelines, assign)
    return False


def improve(order, opts, opt_of, timelines, assign):
    '''Repeats shift-insert and eject-and-relocate on unscheduled requests until no move succeeds.'''
    changed = True
    while changed:
        changed = False
        for u in order:
            if u in assign or not opts[u]:
                continue
            if insert_anywhere(u, opts, opt_of, timelines, assign) or \
               eject_and_relocate(u, opts, opt_of, timelines, assign):
                changed = True


def verify(assign, timelines, opt_of):
    '''Asserts the solution respects the windows, no-overlap, and one placement per request.'''
    seen = set()
    for a, tl in enumerate(timelines):
        for i, (s, e, r) in enumerate(tl):
            assert r not in seen, f"request {r} scheduled more than once"
            seen.add(r)
            assert assign.get(r) == (a, s), f"assign/timeline mismatch for request {r}"
            lo, hi, L = opt_of[r][a]
            assert lo <= s <= hi and e == s + L, f"request {r} on antenna {a} outside its window"
            if i > 0:
                assert tl[i - 1][1] <= s, f"overlap on antenna {a} between requests {tl[i - 1][2]} and {r}"
    assert seen == set(assign), "assign contains requests not on any timeline"


def dispatch_heuristic(problem_data:str, write_results_to_file:bool = False, Timelimit = 60, max_iter = 1000,
                       max_no_improve = 200, seed = 0, upper_bound = None, combine_data:bool = False):
    '''
    Takes in a problem instance, runs the dispatch heuristic with improvement and randomized
    restarts, and returns the best solution, run info, and machine info.
    '''
    start_time = time.time()

    # getting data
    data = read_instance(problem_data, combine_data)
    R, A = data["R"], data["A"]
    opts, opt_of = build_options(data)
    keys = priority_keys(data)
    if upper_bound is None:
        upper_bound = sum(1 for r in range(len(R)) if opts[r])

    rng = random.Random(seed)
    best_assign, best_timelines, best_obj, best_iter = None, None, -1, 0
    iter0_greedy = iter0_obj = None
    no_improve = 0
    iteration = 0
    stop_reason = "IterationLimit"

    while iteration < max_iter:
        order = priority_order(keys, None if iteration == 0 else rng)
        assign, timelines = construct(order, opts, len(A))
        if iteration == 0:
            iter0_greedy = len(assign)
        improve(order, opts, opt_of, timelines, assign)
        if iteration == 0:
            iter0_obj = len(assign)

        if len(assign) > best_obj:
            best_assign, best_timelines, best_obj, best_iter = assign, timelines, len(assign), iteration
            no_improve = 0
        else:
            no_improve += 1
        iteration += 1

        if best_obj >= upper_bound:
            stop_reason = "UpperBoundReached"
            break
        if time.time() - start_time >= Timelimit:
            stop_reason = "TimeLimit"
            break
        if no_improve >= max_no_improve:
            stop_reason = "NoImprovementLimit"
            break

    verify(best_assign, best_timelines, opt_of)

    info = {
        "Objective": best_obj,
        "UpperBound": upper_bound,
        "NumberOfRequests": len(R),
        "Iteration0GreedyObjective": iter0_greedy,
        "Iteration0ImprovedObjective": iter0_obj,
        "BestIteration": best_iter,
        "Iterations": iteration,
        "StopReason": stop_reason,
        "SolveTime": round(time.time() - start_time, 3),
        "TimeLimit": Timelimit,
        "MaxIterations": max_iter,
        "MaxNoImprove": max_no_improve,
        "Seed": seed,
    }

    # getting machine solving context
    processor = str(platform.processor())
    cores = str(os.cpu_count())
    memory = str(psutil.virtual_memory().total)

    if write_results_to_file:
        write_dispatch_results(best_assign, info, processor, cores, memory, problem_data, data, opts)

    return (best_assign, info, processor, cores, memory, problem_data)


def write_dispatch_results(assign, info, processor, cores, memory, problem_data, data, opts):
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
        f.write(f"Upper bound: {info['UpperBound']}\n")
        f.write("\n\n")

        for r in range(len(R)):
            for a in data["A_r"][r]:
                f.write(f" variable name: I_{R[r]}_{A[a]}")
                if r in assign and assign[r][0] == a:
                    lo, hi, L = next((lo, hi, L) for (b, lo, hi, L) in opts[r] if b == a)
                    t = assign[r][1]
                    f.write(f" variable start: {t}")
                    f.write(f" variable end: {t + L}")
                f.write("\n\n")


if __name__ == "__main__":
    import sys
    day = sys.argv[1] if len(sys.argv) > 1 else "12"
    secs = int(sys.argv[2]) if len(sys.argv) > 2 else 60
    _, info, *_ = dispatch_heuristic(day, write_results_to_file=False, Timelimit=secs, combine_data=True)
    for k, v in info.items():
        print(f"{k}: {v}")
