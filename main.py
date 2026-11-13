from CP_model import *
from Instance_reader import *
from Dispatch_rule import *
import sys

def main():
    method = "cp" # "cp" or "dispatch"
    day = 18      # problem day, 12 - 18

    if method == "dispatch":
        dispatch_heuristic(problem_data= str(day), write_results_to_file= True, combine_data= True)
    else:
        cp_model(problem_data= str(day), write_results_to_file= True, Timelimit = int(60), Workers = 4, combine_data= True)
    return


if __name__ == "__main__":
    sys.exit(main())
