# Instance reader: takes data file and puts it into format/structures you need for the algorithms/models

# imports
import pandas as pd
from pathlib import Path

# global variables
folder_path = Path("AFIT_data")

AFIT = [
    "reqlf12.dat", "requp12.dat",
    "reqlf13.dat", "requp13.dat",
    "reqlf14.dat", "requp14.dat",
    "reqlf15.dat", "requp15.dat",
    "reqlf16.dat", "requp16.dat",
    "reqlf17.dat", "requp17.dat",
    "reqlf18.dat", "requp18.dat"
    ]

def read_data(path):
    return pd.read_csv(path,sep=r"\s+",header=None,names=["request_id", "antenna_id","window_start", "window_end","duration", "turnaround_time", "orbit_info"])


def download(file_number, combine:bool = False):
    "' takes in a file number, combines the low and high altititude data if combine = True and "
    "returns a pandas dataframe of the data in the file'"
    "' if combine = False, then file_number is just the file path"

    if combine:
        file_path1 = folder_path/f"reqlf{file_number}.dat"
        file_path2 = folder_path/f"requp{file_number}.dat"
        lf = read_data(file_path1).assign(source="lf")
        up = read_data(file_path2).assign(source="up")
        df = pd.concat([lf, up], ignore_index=True)
        df["request_id"] = df["source"] + "_" + df["request_id"].astype(str)

        return df
    
    else: 
        file_path = folder_path / file_number
        return read_data(file_path)

        
def read_instance(file_number, combine:bool = False):
    "' takes in a file name and returns the data in the file as a dictionary of lists'"

    # download data
    df = download(file_number,combine)

    # convert data to lists
    requests =  df["request_id"]
    antennas =  df["antenna_id"]
    window_start_times =  df["window_start"]
    window_end_times = df["window_end"]
    processing_times = df["duration"]
    turnaround_times = df["turnaround_time"]

    # for each unique request in requests, record window start time, end time, processing time and turnaround time
    unique_requests = requests.unique().tolist()
    unique_antennas = antennas.unique().tolist()
    unique_window_start_times = []
    unique_window_end_times = []
    unique_processing_times = []
    unique_turnaround_times = []
    set_candidate_antennas = []

    antenna_idx = {antenna_id: idx for idx, antenna_id in enumerate(unique_antennas)}

    for request in unique_requests:
        rows = df[df["request_id"] == request]
        win_start_times = set(rows["window_start"])
        win_end_times = set(rows["window_end"])
        proces_times = set(rows["duration"])
        turn_times = set(rows["turnaround_time"])

        # get set of candidate antennas that can serve each request
        antennas = rows["antenna_id"].unique()
        set_candidate_antennas.append([antenna_idx[a] for a in antennas])

        # each request should have a unique window start time, end time, processing time and turnaround time regardless of the antenna processing it
        assert len(win_start_times) == 1, f"expected single unique window start time across all candidate antennas, got {len(win_start_times)}"
        assert len(win_end_times) == 1, f"expected single unique window end time across all candidate antennas, got {len(win_end_times)}"
        assert len(proces_times) == 1, f"expected single processing time across all candidate antennas, got {len(proces_times)}"
        assert len(turn_times) == 1, f"expected single unique turnaround time across all candidate antennas, got {len(turn_times)}"

        unique_window_start_times.append(list(win_start_times)[0])
        unique_window_end_times.append(list(win_end_times)[0])
        unique_processing_times.append(list(proces_times)[0])
        unique_turnaround_times.append(list(turn_times)[0])


    return {
        "R": unique_requests,
        "A": unique_antennas,
        "S_r": unique_window_start_times,
        "E_r": unique_window_end_times,
        "P_r": unique_processing_times,
        "Q_r": unique_turnaround_times,
        "A_r": set_candidate_antennas
    }