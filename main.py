from CP_model import *
from Instance_reader import *
import sys

def main():
    cp_model(problem_data= "reqlf12.dat", write_results_to_file= True, Timelimit = 60, Workers = 4, combine_data= False)
    return


if __name__ == "__main__":
    sys.exit(main())