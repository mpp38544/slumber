import joblib
import numpy as np
import pandas as pd
import wfdb
import os

def run_inference(mode='sensor', input_source='MAX_kevin_data.txt'):
    model = joblib.load("apnea_rf_model.pkl")
    results = {'spo2': [], 'hr': [], 'preds': [], 'actuals': [], 'mode': mode}

    if mode == 'sensor':
        # Load and clean Kevin's data
        hr_c, spo2_c = [], []
        with open(input_source, "r") as f:
            for line in f:
                p = line.split()
                if len(p) < 2: continue
                r_hr, r_o2 = float(p[0]), float(p[1])
                hr_c.append(r_hr if r_hr > 0 else (hr_c[-1] if hr_c else 70.0))
                spo2_c.append(r_o2 if r_o2 > 0 else (spo2_c[-1] if spo2_c else 98.0))
        
        samples_min = 20 * 60 # 20Hz
        for m in range(len(spo2_c)//samples_min):
            s, e = m*samples_min, (m+1)*samples_min
            feat = {'SpO2_Mean': np.mean(spo2_c[s:e]), 'SpO2_Min': np.min(spo2_c[s:e]), 
                    'SpO2_Drop': np.max(spo2_c[s:e])-np.min(spo2_c[s:e]), 'HR_Std': np.std(hr_c[s:e])}
            results['preds'].append(model.predict(pd.DataFrame([feat]))[0])
        results['spo2'], results['hr'] = spo2_c, hr_c

    elif mode == 'dataset':
        rec = wfdb.rdrecord(os.path.join('apnea-ecg-data', input_source))
        ann = wfdb.rdann(os.path.join('apnea-ecg-data', input_source), extension='apn')
        s_idx = next((i for i, n in enumerate(rec.sig_name) if n.lower() in ['spo2', 'sao2']), 0)
        
        fs = rec.fs
        samples_min = int(60 * fs)
        
        # Process every minute that has a label
        for i in range(len(ann.symbol)):
            s, e = i * samples_min, (i + 1) * samples_min
            if e > len(rec.p_signal): break
            
            # Feature extraction
            seg_o2 = rec.p_signal[s:e, s_idx]
            seg_hr = rec.p_signal[s:e, 0] # Assuming HR is channel 0
            
            feat = {'SpO2_Mean': np.mean(seg_o2), 'SpO2_Min': np.min(seg_o2), 
                    'SpO2_Drop': np.max(seg_o2)-np.min(seg_o2), 'HR_Std': np.std(seg_hr)}
            
            results['preds'].append(model.predict(pd.DataFrame([feat]))[0])
            results['actuals'].append(1 if ann.symbol[i] == 'A' else 0)
            
        results['spo2'] = rec.p_signal[:, s_idx]

    return results