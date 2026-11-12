# For models:
# ○ Model constraints and objective function
# ○ Solver (CPLEX/Gurobi)

## Imports
from docplex.cp.model import CpoModel, CpoParameters
import cplex
import os,platform
import psutil
from Instance_reader import *

# defining sets 
global R  # set of all requests
global A  # set of all antennas

# defining parameters 
global A_r  # set of all antennas that can serve request r
global S_ra  # set of all starting times for request r, antenna a visibility window 
global E_ra # set of all ending times for request r, antenna a visibility window
global Q_ra  # set of all turnaround times for request r and antenna a
global P_ra  # set of processing duration times for request r and antenna a

def cp_model(problem_data:str, write_results_to_file:bool = False, Timelimit = 60*30, Workers = 4, combine_data:bool = False):
    '''
    Takes in a problem instance file and defines a cp model and solves it using CPLEX CP Optimizer. 
    Returns the result, solver info, and machine info.
    '''

    # getting data
    data_dict = read_instance(problem_data,combine_data)
    R = data_dict["R"] # list of all requests: idx:request number, value: request name/id
    A = data_dict["A"] # list of all antennas: idx:antenna number, value: antenna name/id
    S_ra = data_dict["S_ra"] # same as above
    E_ra = data_dict["E_ra"] # same as above
    P_ra = data_dict["P_ra"] # same as above
    Q_ra = data_dict["Q_ra"] # same as above
    A_r = data_dict["A_r"] # since we call A_r directly the idx is request idx (number) and the value is a list of candidate antenna idxs (ids)

    # defining CP model
    model = CpoModel(name = problem_data)

    # defining optional interval variable decision variables

    I_ra = [] # optional interval variable for request r and antenna a
    for r in range(0,len(R),1):
        req_list = [None]* len(A)
        for a in A_r[r]:
            req_list[a] = model.interval_var(optional = True,name = "I_{}_{}".format(R[r],A[a]), start = [S_ra[r][a]- Q_ra[r][a], E_ra[r][a] - P_ra[r][a] - Q_ra[r][a]], end = [S_ra[r][a]+P_ra[r][a],E_ra[r][a]], length = P_ra[r][a] + Q_ra[r][a]) # adding optional interval variable for request r and antenna a with start, end, and length constraints
        I_ra.append(req_list)

    B_r = [] # alternative interval variable for request r
    for r in range(0,len(R),1):
        B_r.append(model.interval_var(optional = True,name = "B_{}".format(r+1)))

    # Adding Constraints

    # No overlap constraint
    for a in range(0,len(A),1):
        model.add(model.no_overlap([I_ra[r][a] for r in range(0,len(R),1) if a in A_r[r]])) # no overlap constraint for all interval variables of the same antenna

    # alternative constraint
    for r in range(0,len(R),1):
        model.add(model.alternative(B_r[r],[I_ra[r][a] for a in A_r[r]])) # alternative constraint for all interval variables of the same request

    # add objective function
    model.add(model.maximize(model.sum([model.presence_of(B_r[r]) for r in range(0,len(R),1)]))) # maximize the number of requests that are scheduled

    # solve model
    my_params = CpoParameters(TimeLimit = Timelimit,Workers = Workers, TimeMode = "ElapsedTime") # set time limit in seconds, workers
    result = model.solve(params = my_params) # solve the model with the specified parameters

    # getting model solving context
    solver_info = result.get_solver_infos()

    # getting machine solving context
    processor = str(platform.processor())
    cores = str(os.cpu_count())
    memory = str(psutil.virtual_memory().total)

    if write_results_to_file:
        write_results(result,solver_info,processor,cores,memory,problem_data,I_ra, R, A_r)

    return(result,solver_info,processor,cores,memory, problem_data)

def write_results(result,solver_info,processor,cores,memory, problem_data,I_ra,R,A_r):
    # write results to file
    with open(f"results/{problem_data}.txt","w") as f:
        for k,v in solver_info.items():
            f.write(f"{k}: {v}\n")
        f.write(f"Processor: {processor}\n")
        f.write(f"Cores: {cores}\n")
        f.write(f"Memory: {memory}\n")
        f.write("\n\n")
        if result.is_solution():
            f.write(f"Solution status: {result.get_solve_status()}\n")
            f.write(f"Solution Objective value: {result.get_objective_values()}\n")
            f.write(f"Best Proven Bound: {result.get_objective_bounds()}\n")
            f.write(f"Objective gaps: {result.get_objective_gaps()}\n")
            f.write("\n\n")

            for r in range(0,len(R),1):
                for a in A_r[r]:
                    value = result.get_var_solution(I_ra[r][a])
                    f.write(f" variable name: {value.get_name()}")
                    if value.is_present():
                        f.write(f" variable start: {value.get_start()}")
                        f.write(f" variable end: {value.get_end()}")
                    f.write("\n\n")

