#2. RUN THIS FILE TO GENERATE/TRAIN MODEL
import wfdb
import os
import pandas as pd
import numpy as np
import joblib
from sklearn.ensemble import RandomForestClassifier

# Settings
data_dir = 'apnea-ecg-data'
# CHOOSE WHICH FILES TO TRAIN ON BELOW. make sure the ones you train on have .dat, .hea, and .apn extensions
training_records = ['a01r', 'a02r', 'a03r', 'b01r'] 
model_output = "apnea_rf_model.pkl"

def extract_features(spo2_seg, hr_seg):
    valid_spo2 = spo2_seg[spo2_seg > 50]
    if len(valid_spo2) == 0: return None
    return {
        'SpO2_Mean': np.mean(valid_spo2),
        'SpO2_Min': np.min(valid_spo2),
        'SpO2_Drop': np.max(valid_spo2) - np.min(valid_spo2),
        'HR_Std': np.std(hr_seg) if len(hr_seg) > 0 else 0
    }

all_features = []
print("--- Training Phase ---")
for rec in training_records:
    try:
        record = wfdb.rdrecord(os.path.join(data_dir, rec))
        ann = wfdb.rdann(os.path.join(data_dir, rec), extension='apn')
        
        s_idx = next((i for i, n in enumerate(record.sig_name) if n.lower() in ['spo2', 'sao2']), None)
        h_idx = next((i for i, n in enumerate(record.sig_name) if n.lower() in ['hr', 'pulse', 'ecg']), 0)

        if s_idx is None: continue

        samples_per_min = int(60 * record.fs)
        for i in range(len(ann.symbol)):
            start, end = i * samples_per_min, (i + 1) * samples_per_min
            if end > len(record.p_signal): break
            feat = extract_features(record.p_signal[start:end, s_idx], record.p_signal[start:end, h_idx])
            if feat:
                feat['Label'] = 1 if ann.symbol[i] == 'A' else 0
                all_features.append(feat)
    except Exception as e:
        print(f"Error loading {rec}: {e}")

df = pd.DataFrame(all_features)
rf_model = RandomForestClassifier(n_estimators=100, random_state=42)
rf_model.fit(df.drop('Label', axis=1), df['Label'])
joblib.dump(rf_model, model_output)
print(f"Model saved as {model_output}")