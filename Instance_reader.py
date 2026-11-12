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

    unique_requests = requests.unique().tolist()
    unique_antennas = antennas.unique().tolist()

    antenna_idx = {antenna_id:idx for idx,antenna_id in enumerate(unique_antennas)}
    request_idx = {request_id:idx for idx,request_id in enumerate(unique_requests)}

    # get candidate antennas per request
    set_candidate_antennas = []
    for request in unique_requests:
        rows = df[df["request_id"] == request]

        # get set of candidate antennas that can serve each request
        antennas = rows["antenna_id"].unique()
        set_candidate_antennas.append([antenna_idx[a] for a in antennas])

        assert len(set_candidate_antennas[-1]) <= len(unique_antennas), f"expected at most {len(unique_antennas)} rows, instead got {len(set_candidate_antennas[-1])} rows " # each request can be processed by atmost A antennas (where A is the caridnality of the set of all antennas)


    # initialize lists
    a = len(unique_requests)
    b = len(unique_antennas)
    S_ra = [[None] * b for _ in range(a)]
    E_ra = [[None] * b for _ in range(a)]
    P_ra = [[None] * b for _ in range(a)]
    Q_ra = [[None] * b for _ in range(a)]

    set_request_antenna_pairs = []

    for row in df.itertuples(index=False):
        a = request_idx[row.request_id]
        b = antenna_idx[row.antenna_id]
        S_ra[a][b] = int(row.window_start)
        E_ra[a][b] = int(row.window_end)
        P_ra[a][b] = int(row.duration)
        Q_ra[a][b] = int(row.turnaround_time)

        set_request_antenna_pairs.append((a,b))

    num_unique_request_antenna_pairs = len(set(set_request_antenna_pairs))

    # assumption is that each row is a unique request-antenna pair
    assert num_unique_request_antenna_pairs == len(df), f"each row is not a unique request-antenna pair, recieved {num_unique_request_antenna_pairs} unique request_antenna pairs for {len(df)} total satellite scheduling records " 


    return {
        "R": unique_requests,
        "A": unique_antennas,
        "S_ra": S_ra,
        "E_ra": E_ra,
        "P_ra": P_ra,
        "Q_ra": Q_ra,
        "A_r": set_candidate_antennas
    }