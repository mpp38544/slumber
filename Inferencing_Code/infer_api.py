#!/usr/bin/env python3
import json
import argparse
import os
from updated_inference import infer_from_db

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--minutes', type=int, default=None)
    p.add_argument('--hours', type=int, default=None)
    p.add_argument('--start', default=None)
    p.add_argument('--end', default=None)
    # Default model path: same directory as this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    default_model = os.path.join(script_dir, 'apnea_rf_model.pkl')
    p.add_argument('--model_path', default=default_model)
    p.add_argument('--window_seconds', type=int, default=15, help='Processing window size in seconds (default 15)')
    p.add_argument('--window_stride_seconds', type=int, default=5, help='Window stride in seconds (default 5)')
    p.add_argument('--sensitivity_offset', type=float, default=0.08, help='Sensitivity offset for event detection (default 0.08)')
    args = p.parse_args()

    df = infer_from_db(
        minutes=args.minutes,
        hours=args.hours,
        start_time=args.start,
        end_time=args.end,
        model_path=args.model_path,
        window_seconds=args.window_seconds,
        window_stride_seconds=args.window_stride_seconds,
        sensitivity_offset=args.sensitivity_offset,
    )

    # Build JSON-serializable structure
    out = {
        'start_ts': [],
        'end_ts': [],
        'window_end_idx': [],
        'pred': [],
        'event_flag': [],
        'event_type': [],
        'event_reason': [],
        'event_severity': [],
        'SpO2_Mean': [],
        'SpO2_Min': [],
        'SpO2_Drop': [],
        'HR_Std': []
    }

    for _, row in df.iterrows():
        start = row['start_ts']
        end = row['end_ts']
        # Ensure ISO string
        out['start_ts'].append(str(start))
        out['end_ts'].append(str(end))
        out['window_end_idx'].append(int(row['window_end_idx']))
        out['pred'].append(int(row['pred']))
        out['event_flag'].append(int(row.get('event_flag', row['pred'])))
        out['event_type'].append(str(row.get('event_type', 'normal')))
        out['event_reason'].append(str(row.get('event_reason', 'normal')))
        out['event_severity'].append(float(row.get('event_severity', 0.0)))
        out['SpO2_Mean'].append(float(row['SpO2_Mean']))
        out['SpO2_Min'].append(float(row['SpO2_Min']))
        out['SpO2_Drop'].append(float(row['SpO2_Drop']))
        out['HR_Std'].append(float(row['HR_Std']))

    print(json.dumps(out))

if __name__ == '__main__':
    main()
