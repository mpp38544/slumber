#1. RUN THIS SCRIPT TO DOWNLOAD SLEEP APNEA DATA FROM ONLINE (it takes quite long)

import wfdb

# This will download the entire Apnea-ECG database to a local folder
wfdb.dl_database('apnea-ecg', dl_dir='./apnea-ecg-data')