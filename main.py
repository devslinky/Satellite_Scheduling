from CP_model import *
from Instance_reader import *
from Dispatch_rule import *
import sys

def main():
    cp_model(problem_data= str(18), write_results_to_file= True, Timelimit = int(60), Workers = 4, combine_data= True)
    return


if __name__ == "__main__":
    sys.exit(main())