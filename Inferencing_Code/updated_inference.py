import joblib
import numpy as np
import pandas as pd
import wfdb
import os
import mysql.connector
from datetime import datetime, timedelta

def run_inference(mode='sensor', input_source='MAX_kevin_data.txt', db_source='latest'):
    """
    Run inference on apnea data
    
    Modes:
    - 'sensor' with input_source='file': Read from text file
    - 'sensor' with input_source='database': Read from MySQL database
    - 'dataset': Read from wfdb dataset
    
    db_source options:
    - 'latest': Get the most recent N records
    - 'hours=6': Get data from last 6 hours
    - 'all': Get all data from database
    - 'date_range': Specify start_time and end_time as parameters
    """
    
    model = joblib.load("apnea_rf_model.pkl")
    results = {'spo2': [], 'hr': [], 'preds': [], 'actuals': [], 'mode': mode}

    if mode == 'sensor':
        if input_source == 'database':
            # Load from MySQL database
            hr_c, spo2_c, timestamps = load_from_database(db_source)
        else:
            # Load from text file (original code)
            hr_c, spo2_c = [], []
            with open(input_source, "r") as f:
                for line in f:
                    p = line.split()
                    if len(p) < 2: 
                        continue
                    r_hr, r_o2 = float(p[0]), float(p[1])
                    hr_c.append(r_hr if r_hr > 0 else (hr_c[-1] if hr_c else 70.0))
                    spo2_c.append(r_o2 if r_o2 > 0 else (spo2_c[-1] if spo2_c else 98.0))
        
        # Process data in 1-minute chunks (20Hz = 20 samples/sec = 1200 samples/min)
        samples_min = 20 * 60  # 20Hz sampling rate
        for m in range(len(spo2_c) // samples_min):
            s, e = m * samples_min, (m + 1) * samples_min
            
            # Extract features from this minute
            feat = {
                'SpO2_Mean': np.mean(spo2_c[s:e]), 
                'SpO2_Min': np.min(spo2_c[s:e]), 
                'SpO2_Drop': np.max(spo2_c[s:e]) - np.min(spo2_c[s:e]), 
                'HR_Std': np.std(hr_c[s:e])
            }
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
            if e > len(rec.p_signal): 
                break
            
            # Feature extraction
            seg_o2 = rec.p_signal[s:e, s_idx]
            seg_hr = rec.p_signal[s:e, 0]  # Assuming HR is channel 0
            
            feat = {
                'SpO2_Mean': np.mean(seg_o2), 
                'SpO2_Min': np.min(seg_o2), 
                'SpO2_Drop': np.max(seg_o2) - np.min(seg_o2), 
                'HR_Std': np.std(seg_hr)
            }
            
            results['preds'].append(model.predict(pd.DataFrame([feat]))[0])
            results['actuals'].append(1 if ann.symbol[i] == 'A' else 0)
            
        results['spo2'] = rec.p_signal[:, s_idx]

    return results


def load_from_database(db_source='latest', num_records=None, minutes=None, hours=None,
                       start_time=None, end_time=None, include_flex=False):
    """
    Load sensor data from MySQL database
    
    Parameters:
    - db_source: 'latest' (last num_records), 'hours' (last N hours), 'all', or 'custom'
    - num_records: How many recent records to get (default 1200 = 1 min at 20Hz)
    - minutes: Get data from last N minutes
    - hours: Get data from last N hours
    - start_time, end_time: Custom date range (datetime objects or strings)
    - include_flex: Return flex voltage values when True
    
    Returns:
    - hr_data: List of heart rate values
    - spo2_data: List of SpO2 values
    """
    
    # Database connection
    conn = mysql.connector.connect(
        host="localhost",
        user="root",
        password="",
        database="db_health"
    )
    cursor = conn.cursor()
    
    hr_data = []
    spo2_data = []
    flex_data = []
    timestamps = []
    
    try:
        if db_source == 'latest':
            # Get the most recent N records
            if num_records is None:
                num_records = 1200  # 1 minute at 20Hz
            
            if include_flex:
                query = f"""
                    SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
                    ORDER BY created_at DESC 
                    LIMIT {num_records}
                """
            else:
                query = f"""
                    SELECT hr, spo2, created_at FROM tbl_vitals 
                    ORDER BY created_at DESC 
                    LIMIT {num_records}
                """
            cursor.execute(query)
            
            # Reverse to get chronological order (oldest to newest)
            rows = list(reversed(cursor.fetchall()))
            
        elif db_source == 'all':
            # Get all data
            query = "SELECT hr, spo2, created_at FROM tbl_vitals ORDER BY created_at ASC"
            cursor.execute(query)
            rows = cursor.fetchall()
            
        elif db_source == 'minutes':
            if minutes is None:
                minutes = 5

            if include_flex:
                query = f"""
                    SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL {minutes} MINUTE)
                    ORDER BY created_at ASC
                """
            else:
                query = f"""
                    SELECT hr, spo2, created_at FROM tbl_vitals
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL {minutes} MINUTE)
                    ORDER BY created_at ASC
                """
            cursor.execute(query)
            rows = cursor.fetchall()

        elif db_source == 'hours':
            # Get data from last N hours
            if hours is None:
                hours = 1
            
            if include_flex:
                query = f"""
                    SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL {hours} HOUR)
                    ORDER BY created_at ASC
                """
            else:
                query = f"""
                    SELECT hr, spo2, created_at FROM tbl_vitals 
                    WHERE created_at >= DATE_SUB(NOW(), INTERVAL {hours} HOUR)
                    ORDER BY created_at ASC
                """
            cursor.execute(query)
            rows = cursor.fetchall()
            
        elif db_source == 'custom':
            # Custom date range
            if start_time is None or end_time is None:
                raise ValueError("start_time and end_time required for custom range")
            
            if include_flex:
                query = """
                    SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
                    WHERE created_at BETWEEN %s AND %s
                    ORDER BY created_at ASC
                """
            else:
                query = """
                    SELECT hr, spo2, created_at FROM tbl_vitals 
                    WHERE created_at BETWEEN %s AND %s
                    ORDER BY created_at ASC
                """
            cursor.execute(query, (start_time, end_time))
            rows = cursor.fetchall()
        
        else:
            raise ValueError(f"Unknown db_source: {db_source}")
        
        # Convert rows to lists, handling bad data
        for row in rows:
            if include_flex:
                hr, spo2, flex_voltage, created_at = row
            else:
                hr, spo2, created_at = row
                flex_voltage = None

            # Clean the data (same as text file version)
            hr_data.append(hr if hr > 0 else (hr_data[-1] if hr_data else 70.0))
            spo2_data.append(spo2 if spo2 > 0 else (spo2_data[-1] if spo2_data else 98.0))
            if include_flex:
                flex_data.append(float(flex_voltage) if flex_voltage is not None else (flex_data[-1] if flex_data else 0.0))
            timestamps.append(created_at)
        
    finally:
        cursor.close()
        conn.close()
    
    if include_flex:
        return hr_data, spo2_data, flex_data, timestamps
    return hr_data, spo2_data, timestamps


def detect_flex_breathing_alerts(
    flex_data,
    timestamps=None,
    sampling_rate=20,
    window_seconds=8,
    window_stride_seconds=3,
    smoothing_window=3,
    sensitivity_offset=0.15,
):
    """
    Create rule-based breathing alerts from the flex sensor waveform.

    Status meanings:
    - normal: window looks similar to the local breathing baseline
    - underexerted: low motion and low peak activity, which can indicate shallow breathing or a pause
    - breath_hold: sustained low activity across consecutive windows, which can indicate apnea-like breath holding
    - overexerted: unusually high motion and peak activity, which can indicate labored or strained breathing
    """

    flex = np.asarray(flex_data, dtype=float)
    if flex.size == 0:
        return pd.DataFrame(columns=[
            'start_ts', 'end_ts', 'window_start_idx', 'window_end_idx',
            'amplitude', 'motion', 'breaths_per_min', 'peak_count', 'status',
            'severity', 'notification'
        ])

    smooth_window = max(3, int(smoothing_window))
    if smooth_window > 1:
        kernel = np.ones(smooth_window, dtype=float) / smooth_window
        smoothed = np.convolve(flex, kernel, mode='same')
    else:
        smoothed = flex.copy()

    window_size = max(1, int(window_seconds * sampling_rate))
    window_stride = max(1, int(window_stride_seconds * sampling_rate))
    if window_size > len(smoothed):
        window_size = len(smoothed)
    if window_stride > window_size:
        window_stride = max(1, window_size // 2)

    raw_windows = []
    for start_idx in range(0, len(smoothed), window_stride):
        end_idx = min(start_idx + window_size, len(smoothed))
        segment = smoothed[start_idx:end_idx]
        if len(segment) < max(5, sampling_rate // 2):
            continue

        diff = np.diff(segment)
        amplitude = float(np.percentile(segment, 95) - np.percentile(segment, 5))
        motion = float(np.std(diff)) if len(diff) else 0.0
        centered = segment - np.median(segment)
        zero_crossings = int(np.sum(np.diff(np.signbit(centered)) != 0))

        slope = np.sign(diff)
        candidates = np.where((slope[:-1] > 0) & (slope[1:] <= 0))[0] + 1 if len(slope) > 1 else []
        prominence_floor = max(
            amplitude * (0.18 - sensitivity_offset * 0.05),
            float(np.std(segment)) * (0.35 - sensitivity_offset * 0.05),
            1e-6,
        )
        peak_count = 0
        for candidate in candidates:
            left = max(0, candidate - 2)
            right = min(len(segment), candidate + 3)
            local = segment[left:right]
            if len(local) and segment[candidate] - np.min(local) >= prominence_floor:
                peak_count += 1

        breaths_per_min = float(peak_count * 60.0 / max(window_seconds, 1))
        oscillation_ratio = float(peak_count / max(window_seconds / 2.5, 1.0))
        raw_windows.append({
            'window_start_idx': start_idx,
            'window_end_idx': end_idx - 1,
            'amplitude': amplitude,
            'motion': motion,
            'zero_crossings': zero_crossings,
            'breaths_per_min': breaths_per_min,
            'peak_count': int(peak_count),
            'oscillation_ratio': oscillation_ratio,
        })

    if not raw_windows:
        return pd.DataFrame(columns=[
            'start_ts', 'end_ts', 'window_start_idx', 'window_end_idx',
            'amplitude', 'motion', 'zero_crossings', 'breaths_per_min', 'peak_count', 'oscillation_ratio', 'status',
            'severity', 'notification'
        ])

    overall_amp = float(np.percentile(flex, 95) - np.percentile(flex, 5))
    overall_motion = float(np.std(np.diff(smoothed))) if len(smoothed) > 1 else 0.0
    overall_std = float(np.std(smoothed)) if len(smoothed) else 0.0
    flat_amp_threshold = max(overall_amp * max(0.08, 0.14 - sensitivity_offset * 0.03), overall_std * 0.20, 1e-6)
    low_motion_threshold = max(overall_motion * max(0.40, 0.60 - sensitivity_offset * 0.15), 1e-6)
    high_amp_threshold = max(overall_amp * max(1.20, 1.35 - sensitivity_offset * 0.08), overall_std * 0.80, 1e-6)

    alerts = []
    for window in raw_windows:
        amp_ratio = window['amplitude'] / overall_amp if overall_amp else 1.0
        motion_ratio = window['motion'] / overall_motion if overall_motion else 1.0
        bpm_ratio = window['breaths_per_min'] / 12.0 if window['breaths_per_min'] else 0.0
        irregular_oscillation = window['peak_count'] <= 1 or window['oscillation_ratio'] < (0.35 + sensitivity_offset * 0.15)

        breath_hold_like = (
            window['peak_count'] == 0
            and window['motion'] < low_motion_threshold
            and window['amplitude'] < flat_amp_threshold
        )
        low_activity = (
            window['peak_count'] <= 1
            and window['amplitude'] < flat_amp_threshold * 0.9
            and window['motion'] < low_motion_threshold * 0.9
        )
        rapid_breathing_like = (
            window['peak_count'] >= 3
            and window['breaths_per_min'] >= 18.0
            and window['oscillation_ratio'] >= max(1.0, 1.0 - sensitivity_offset * 0.05)
            and window['motion'] >= low_motion_threshold * 0.75
        )
        high_activity = window['amplitude'] > high_amp_threshold and (window['motion'] > low_motion_threshold * 1.25 or window['peak_count'] >= 4)

        if breath_hold_like:
            status = 'breath_hold'
            notification = 'Sustained low flex activity suggests a breath hold or apnea-like pause.'
        elif rapid_breathing_like:
            status = 'rapid_breathing'
            notification = 'Frequent flex oscillations suggest rapid breathing or fast shallow breaths.'
        elif low_activity:
            status = 'underexerted'
            notification = 'Possible shallow breathing or a breathing pause detected.'
        elif high_activity:
            status = 'overexerted'
            notification = 'Possible labored breathing or respiratory struggle detected.'
        else:
            status = 'normal'
            notification = 'Breathing activity is within the local baseline range.'

        severity = float(max(
            abs(1.0 - amp_ratio),
            abs(1.0 - motion_ratio),
            abs(1.0 - max(bpm_ratio, 0.0) / 12.0 if bpm_ratio else 1.0)
        ))
        start_ts = timestamps[window['window_start_idx']] if timestamps and window['window_start_idx'] < len(timestamps) else None
        end_ts = timestamps[window['window_end_idx']] if timestamps and window['window_end_idx'] < len(timestamps) else None

        alerts.append({
            'start_ts': start_ts,
            'end_ts': end_ts,
            **window,
            'status': status,
            'severity': severity,
            'notification': notification,
        })

    return pd.DataFrame.from_records(alerts)


def infer_from_db(db_source='latest', num_records=1200, minutes=None, hours=None, model_path="apnea_rf_model.pkl"):
    """
    Run inference on database data in 1-minute windows and return a pandas DataFrame

    Returns columns: start_ts, end_ts, window_end_idx, SpO2_Mean, SpO2_Min, SpO2_Drop, HR_Std, pred
    """
    model = joblib.load(model_path)

    if minutes is not None:
        db_source = 'minutes'
    elif hours is not None:
        db_source = 'hours'

    hr_c, spo2_c, timestamps = load_from_database(db_source, num_records=num_records, minutes=minutes, hours=hours)
    samples_min = 20 * 60
    if len(spo2_c) < samples_min:
        # Fall back to a single window when there is not yet a full minute of data.
        samples_min = len(spo2_c)
    records = []

    if samples_min == 0:
        return pd.DataFrame.from_records([])

    for m in range(max(1, len(spo2_c) // samples_min)):
        s, e = m * samples_min, (m + 1) * samples_min
        if e > len(spo2_c):
            e = len(spo2_c)
        seg_hr = hr_c[s:e]
        seg_o2 = spo2_c[s:e]

        if len(seg_hr) == 0 or len(seg_o2) == 0:
            continue

        feat = {
            'SpO2_Mean': np.mean(seg_o2),
            'SpO2_Min': np.min(seg_o2),
            'SpO2_Drop': np.max(seg_o2) - np.min(seg_o2),
            'HR_Std': np.std(seg_hr)
        }

        pred = int(model.predict(pd.DataFrame([feat]))[0])
        start_ts = timestamps[s] if s < len(timestamps) else None
        end_ts = timestamps[e-1] if (e-1) < len(timestamps) else None

        records.append({
            'start_ts': start_ts,
            'end_ts': end_ts,
            'window_end_idx': e - 1,
            **feat,
            'pred': pred
        })

    df = pd.DataFrame.from_records(records)
    return df
    # New function definition with sliding window logic
def infer_from_db(
    db_source='latest',
    num_records=1200,
    minutes=None,
    hours=None,
    start_time=None,
    end_time=None,
    model_path="apnea_rf_model.pkl",
    window_seconds=30,
    window_stride_seconds=15,
    sensitivity_offset=0.08,
):
    """
    Run inference on database data in sliding time windows and return a pandas DataFrame.

    Returns columns: start_ts, end_ts, window_start_idx, window_end_idx, SpO2_Mean, SpO2_Min,
    SpO2_Drop, HR_Std, pred, event_flag, event_type, event_reason, event_severity.
    """
    model = joblib.load(model_path)

    if start_time is not None and end_time is not None:
        db_source = 'custom'
    elif minutes is not None:
        db_source = 'minutes'
    elif hours is not None:
        db_source = 'hours'

    hr_c, spo2_c, flex_c, timestamps = load_from_database(
        db_source,
        num_records=num_records,
        minutes=minutes,
        hours=hours,
        start_time=start_time,
        end_time=end_time,
        include_flex=True,
    )

    if len(spo2_c) == 0:
        return pd.DataFrame.from_records([])

    frame = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps),
        'hr': pd.to_numeric(pd.Series(hr_c), errors='coerce'),
        'spo2': pd.to_numeric(pd.Series(spo2_c), errors='coerce'),
        'flex': pd.to_numeric(pd.Series(flex_c if flex_c else [0.0] * len(hr_c)), errors='coerce'),
    }).dropna(subset=['timestamp']).reset_index(drop=True)

    if frame.empty:
        return pd.DataFrame.from_records([])

    frame['hr'] = frame['hr'].ffill().bfill()
    frame['spo2'] = frame['spo2'].ffill().bfill()
    frame['flex'] = frame['flex'].ffill().bfill().fillna(0.0)
    frame = frame.sort_values('timestamp').reset_index(drop=True)

    timestamp_diffs = frame['timestamp'].diff().dt.total_seconds().dropna()
    estimated_sampling_rate = 10.0
    if not timestamp_diffs.empty:
        median_delta = float(timestamp_diffs.median())
        if median_delta > 0:
            estimated_sampling_rate = max(1.0, 1.0 / median_delta)

    rapid_flex_alerts = detect_flex_breathing_alerts(
        frame['flex'].to_numpy(),
        timestamps=frame['timestamp'].tolist(),
        sampling_rate=int(round(estimated_sampling_rate)),
        window_seconds=6,
        window_stride_seconds=2,
        sensitivity_offset=sensitivity_offset,
    )

    timestamps_np = frame['timestamp'].to_numpy()
    window_delta = pd.Timedelta(seconds=max(1, int(window_seconds)))
    stride_delta = pd.Timedelta(seconds=max(1, int(window_stride_seconds)))
    if stride_delta > window_delta:
        stride_delta = max(pd.Timedelta(seconds=1), window_delta / 2)

    overall_hr = frame['hr'].astype(float)
    overall_spo2 = frame['spo2'].astype(float)
    overall_flex = frame['flex'].astype(float)

    overall_hr_std = float(overall_hr.std(ddof=0)) if len(overall_hr) else 0.0
    overall_spo2_std = float(overall_spo2.std(ddof=0)) if len(overall_spo2) else 0.0
    overall_flex_std = float(overall_flex.std(ddof=0)) if len(overall_flex) else 0.0
    overall_flex_amp = float(np.percentile(overall_flex, 95) - np.percentile(overall_flex, 5)) if len(overall_flex) else 0.0
    overall_flex_motion = float(np.std(np.diff(overall_flex))) if len(overall_flex) > 1 else 0.0

    hr_low_extreme = max(48.0, float(overall_hr.quantile(0.10)) - 4.0)
    hr_high_extreme = min(115.0, float(overall_hr.quantile(0.90)) + 4.0)
    spo2_low_extreme = max(88.0, float(overall_spo2.quantile(0.10)) - 1.0)
    spo2_drop_threshold = max(2.0, overall_spo2_std * (0.9 + sensitivity_offset * 0.3))
    flex_flat_threshold = max(overall_flex_amp * max(0.10, 0.18 - sensitivity_offset * 0.04), overall_flex_std * 0.40, 1e-6)
    flex_high_threshold = max(overall_flex_amp * (1.20 - sensitivity_offset * 0.05), overall_flex_std * 1.10, 1e-6)
    flex_jump_threshold = max(overall_flex_amp * 0.50, overall_flex_std * 0.75, 1e-6)
    hr_jump_threshold = max(8.0, overall_hr_std * (1.0 + sensitivity_offset))
    spo2_jump_threshold = max(1.5, overall_spo2_std * (0.8 + sensitivity_offset))
    low_flex_motion_threshold = max(overall_flex_motion * 0.8, 1e-6)

    records = []
    low_flex_streak = 0
    prev_window = None

    start_time = frame['timestamp'].iloc[0].floor('min')
    last_time = frame['timestamp'].iloc[-1].ceil('min')
    current_start = start_time

    while current_start <= last_time:
        current_end = current_start + window_delta
        start_idx = int(np.searchsorted(timestamps_np, np.datetime64(current_start), side='left'))
        end_idx = int(np.searchsorted(timestamps_np, np.datetime64(current_end), side='left'))
        window = frame.iloc[start_idx:end_idx]

        if len(window) < 3:
            current_start += stride_delta
            continue

        seg_hr = window['hr'].astype(float).to_numpy()
        seg_o2 = window['spo2'].astype(float).to_numpy()
        seg_flex = window['flex'].astype(float).to_numpy()

        feat = {
            'SpO2_Mean': float(np.mean(seg_o2)),
            'SpO2_Min': float(np.min(seg_o2)),
            'SpO2_Drop': float(np.max(seg_o2) - np.min(seg_o2)),
            'HR_Std': float(np.std(seg_hr)),
        }

        feat_df = pd.DataFrame([feat])
        pred_prob = None
        if hasattr(model, 'predict_proba'):
            pred_prob = float(model.predict_proba(feat_df)[0][1])
            pred = 1 if pred_prob >= 0.85 else 0
        else:
            pred = int(model.predict(feat_df)[0])
        hr_mean = float(np.mean(seg_hr))
        hr_min = float(np.min(seg_hr))
        hr_max = float(np.max(seg_hr))
        hr_std = float(np.std(seg_hr))
        hr_delta = float(abs(seg_hr[-1] - seg_hr[0])) if len(seg_hr) > 1 else 0.0

        spo2_mean = float(np.mean(seg_o2))
        spo2_min = float(np.min(seg_o2))
        spo2_max = float(np.max(seg_o2))
        spo2_drop = float(spo2_max - spo2_min)
        spo2_delta = float(abs(seg_o2[-1] - seg_o2[0])) if len(seg_o2) > 1 else 0.0

        flex_mean = float(np.mean(seg_flex))
        flex_amp = float(np.percentile(seg_flex, 95) - np.percentile(seg_flex, 5))
        flex_motion = float(np.std(np.diff(seg_flex))) if len(seg_flex) > 1 else 0.0
        flex_delta = float(abs(seg_flex[-1] - seg_flex[0])) if len(seg_flex) > 1 else 0.0
        rapid_overlap = False
        if rapid_flex_alerts is not None and not rapid_flex_alerts.empty:
            current_window_end_idx = max(start_idx, end_idx - 1)
            rapid_overlap = bool(((rapid_flex_alerts['status'] == 'rapid_breathing') & (rapid_flex_alerts['window_end_idx'] >= start_idx) & (rapid_flex_alerts['window_start_idx'] <= current_window_end_idx)).any())

        reasons = []
        model_event_confident = pred == 1 and (pred_prob is None or pred_prob >= 0.9)
        if pred == 1:
            reasons.append('model apnea prediction')

        if hr_mean <= hr_low_extreme or hr_mean >= hr_high_extreme:
            reasons.append('extreme heart rate')
        if hr_delta >= hr_jump_threshold or hr_std >= max(8.0, overall_hr_std * (1.15 + sensitivity_offset * 0.25)):
            reasons.append('sudden heart rate change')

        if spo2_mean <= spo2_low_extreme or spo2_min <= 90.0 or spo2_drop >= spo2_drop_threshold:
            reasons.append('extreme oxygen saturation')
        if spo2_delta >= spo2_jump_threshold:
            reasons.append('sudden SpO2 change')

        if rapid_overlap:
            reasons.append('rapid breathing')

        if flex_amp <= flex_flat_threshold and flex_motion <= low_flex_motion_threshold:
            low_flex_streak += 1
            reasons.append('low flex activity')
            if low_flex_streak >= 3:
                reasons.append('flex breath hold')
        elif flex_amp >= flex_high_threshold or flex_motion >= max(low_flex_motion_threshold * 1.5, overall_flex_motion * 1.2):
            low_flex_streak = 0
            reasons.append('high flex activity')
        elif prev_window is not None and abs(flex_mean - prev_window['flex_mean']) >= flex_jump_threshold:
            low_flex_streak = 0
            reasons.append('sudden flex change')
        else:
            low_flex_streak = 0

        event_flag = 1 if any(reason != 'model apnea prediction' for reason in reasons) else 0
        if event_flag == 0 and model_event_confident:
            event_flag = 1

        if event_flag:
            if 'flex breath hold' in reasons:
                event_type = 'breath_hold'
            elif 'rapid breathing' in reasons:
                event_type = 'rapid_breathing'
            elif 'high flex activity' in reasons:
                event_type = 'overexerted'
            elif 'low flex activity' in reasons:
                event_type = 'underexerted'
            elif 'extreme oxygen saturation' in reasons or 'extreme heart rate' in reasons:
                event_type = 'vital_extreme'
            elif 'sudden flex change' in reasons or 'sudden SpO2 change' in reasons or 'sudden heart rate change' in reasons:
                event_type = 'sudden_change'
            else:
                event_type = 'model_event'
        else:
            event_type = 'normal'

        event_severity = float(min(3.0, len([reason for reason in reasons if reason != 'model apnea prediction']) + (1.0 if pred == 1 else 0.0)))
        start_ts = window['timestamp'].iloc[0]
        end_ts = window['timestamp'].iloc[-1]

        records.append({
            'start_ts': start_ts,
            'end_ts': end_ts,
            'window_start_idx': start_idx,
            'window_end_idx': window.index[-1],
            **feat,
            'pred': pred,
            'event_flag': event_flag,
            'event_type': event_type,
            'event_reason': '; '.join(reasons) if reasons else 'normal',
            'event_severity': event_severity,
            'HR_Mean': hr_mean,
            'HR_Min': hr_min,
            'HR_Max': hr_max,
            'HR_Delta': hr_delta,
            'SpO2_Mean_Raw': spo2_mean,
            'SpO2_Min_Raw': spo2_min,
            'SpO2_Max_Raw': spo2_max,
            'SpO2_Delta': spo2_delta,
            'Flex_Mean': flex_mean,
            'Flex_Amp': flex_amp,
            'Flex_Motion': flex_motion,
            'Flex_Delta': flex_delta,
        })

        prev_window = {
            'flex_mean': flex_mean,
        }
        current_start += stride_delta

    df = pd.DataFrame.from_records(records)
    return df


if __name__ == "__main__":
    # Example: run inference on latest records and save to CSV
    df = infer_from_db('latest', num_records=1200)
    print(df.head())
    df.to_csv('inference_results.csv', index=False)