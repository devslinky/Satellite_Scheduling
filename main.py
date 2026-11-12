from CP_model import *
from Instance_reader import *
from Dispatch_rule import *
import sys

def main():
    data = input("input day of problem i.e. 12: ") # i.e 12
    write_results = input("do you want to write results to file (y/n)?: ") # i.e y
    if write_results == "y":
        write = True
    else: write= False   

    seconds = input("how long do you want to run program for? (in seconds): ") # i.e 60 : which is a minute
    

    cp_model(problem_data= data, write_results_to_file= write, Timelimit = int(seconds), Workers = 4, combine_data= True)
    return


if __name__ == "__main__":
    sys.exit(main())