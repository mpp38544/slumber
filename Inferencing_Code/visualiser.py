#3. RUN THIS FILE TO PREDICT ON NEW DATA AND GENERATE A PLOT

import matplotlib.pyplot as plt
import numpy as np
from inference import run_inference
from sklearn.metrics import classification_report
import argparse
import sys
import pandas as pd
from updated_inference import load_from_database, infer_from_db, detect_flex_breathing_alerts
from inference import run_inference as legacy_run_inference
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def _attach_hover_tooltip(fig, ax, patches):
    annotation = ax.annotate(
        '',
        xy=(0, 0),
        xytext=(12, 12),
        textcoords='offset points',
        ha='left',
        va='bottom',
        fontsize=8,
        bbox=dict(boxstyle='round,pad=0.35', fc='white', ec='0.3', alpha=0.95),
        arrowprops=dict(arrowstyle='->', color='0.25', lw=0.8),
    )
    annotation.set_visible(False)

    def on_move(event):
        if event.inaxes != ax:
            if annotation.get_visible():
                annotation.set_visible(False)
                fig.canvas.draw_idle()
            return

        for patch in patches:
            contains, _ = patch.contains(event)
            if contains:
                hover_text = getattr(patch, '_hover_text', None)
                if hover_text:
                    annotation.xy = (event.xdata, event.ydata)
                    annotation.set_text(hover_text)
                    annotation.set_visible(True)
                    fig.canvas.draw_idle()
                return

        if annotation.get_visible():
            annotation.set_visible(False)
            fig.canvas.draw_idle()

    fig.canvas.mpl_connect('motion_notify_event', on_move)


def plot_dataset_predictions(input_source='a04r'):
    data = legacy_run_inference(mode='dataset', input_source=input_source)

    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    samples_per_min = int(len(data['spo2']) / len(data['actuals'])) if data['actuals'] else 1
    actual_span_patches = []
    pred_span_patches = []

    ax1.plot(data['spo2'], color='blue', alpha=0.6, label='Raw SpO2')
    ax1.set_title('Apnea Analysis: Ground Truth vs Prediction')
    ax1.set_ylabel('SpO2 %')

    for i, act in enumerate(data['actuals']):
        color = 'green' if act == 0 else 'red'
        patch = ax2.axvspan(i * samples_per_min, (i + 1) * samples_per_min, color=color, alpha=0.3)
        patch._hover_text = f"Actual label: {'Normal' if act == 0 else 'Apnea'}\nDoctor annotation for this minute."
        actual_span_patches.append(patch)
    ax2.set_ylabel('Actual Label\n(Doctor)')
    ax2.set_yticks([])

    for i, pred in enumerate(data['preds']):
        color = 'green' if pred == 0 else 'red'
        patch = ax3.axvspan(i * samples_per_min, (i + 1) * samples_per_min, color=color, alpha=0.3)
        patch._hover_text = f"Model prediction: {'Normal' if pred == 0 else 'Apnea'}\nAI output for this minute."
        pred_span_patches.append(patch)
    ax3.set_ylabel('AI Prediction\n(Model)')
    ax3.set_xlabel('Samples (Seconds if 1Hz)')

    ax2.legend(
        handles=[
            Patch(facecolor='green', alpha=0.3, label='Normal'),
            Patch(facecolor='red', alpha=0.3, label='Apnea'),
        ],
        title='Actual label colours',
        loc='upper right',
        fontsize=8,
    )
    ax3.legend(
        handles=[
            Patch(facecolor='green', alpha=0.3, label='Normal'),
            Patch(facecolor='red', alpha=0.3, label='Apnea'),
        ],
        title='Prediction colours',
        loc='upper right',
        fontsize=8,
    )

    for i in range(len(data['preds'])):
        if data['preds'][i] != data['actuals'][i]:
            ax1.vlines(i * samples_per_min + (samples_per_min / 2), 70, 100,
                       color='orange', linestyles='dotted', alpha=0.5)

    _attach_hover_tooltip(fig, ax2, actual_span_patches)
    _attach_hover_tooltip(fig, ax3, pred_span_patches)

    plt.tight_layout()
    plt.show()
    print('\n--- Validation Statistics ---')
    print(classification_report(data['actuals'], data['preds'], target_names=['Normal', 'Apnea']))


def plot_database_flex_alerts(db_source='latest', minutes=None, hours=None, num_records=1200):
    hr, spo2, flex, timestamps = load_from_database(
        db_source=db_source,
        num_records=num_records,
        minutes=minutes,
        hours=hours,
        include_flex=True,
    )

    if not timestamps:
        print('No database rows found for the selected view length.')
        return

    df_inf = infer_from_db(db_source=db_source, num_records=num_records, minutes=minutes, hours=hours)
    df_alerts = detect_flex_breathing_alerts(flex, timestamps=timestamps)

    timestamps = pd.to_datetime(timestamps)
    fig, axes = plt.subplots(4, 1, figsize=(15, 12), sharex=True)

    axes[0].plot(timestamps, hr, color='tab:red', linewidth=1.2)
    axes[0].set_ylabel('HR (BPM)')
    axes[0].set_title('Vitals with model predictions and flex-based breathing alerts')
    axes[0].grid(True, alpha=0.25)

    axes[1].plot(timestamps, spo2, color='tab:blue', linewidth=1.2)
    axes[1].set_ylabel('SpO2 (%)')
    axes[1].grid(True, alpha=0.25)

    axes[2].plot(timestamps, flex, color='tab:orange', linewidth=1.2)
    axes[2].set_ylabel('Flex Voltage (V)')
    axes[2].grid(True, alpha=0.25)

    axes[3].set_ylim(0, 1)
    axes[3].set_yticks([])
    axes[3].set_ylabel('Alert')
    axes[3].grid(False)

    for _, row in df_inf.iterrows():
        start_ts = pd.to_datetime(row['start_ts']) if pd.notna(row['start_ts']) else None
        end_ts = pd.to_datetime(row['end_ts']) if pd.notna(row['end_ts']) else None
        if start_ts is None or end_ts is None:
            continue
        color = 'tab:red' if int(row['pred']) == 1 else 'tab:green'
        for ax in axes[:2]:
            patch = ax.axvspan(start_ts, end_ts, color=color, alpha=0.08)
            patch._hover_text = f"Model prediction: {'Apnea' if int(row['pred']) == 1 else 'Normal'}\n{start_ts} to {end_ts}"

    axes[0].legend(
        handles=[Line2D([0], [0], color='tab:red', lw=1.2, label='HR trace')],
        loc='upper right',
        fontsize=8,
    )
    axes[1].legend(
        handles=[Line2D([0], [0], color='tab:blue', lw=1.2, label='SpO2 trace')],
        loc='upper right',
        fontsize=8,
    )

    status_colors = {
        'underexerted': 'tab:purple',
        'rapid_breathing': 'tab:cyan',
        'overexerted': 'tab:red',
        'normal': 'tab:green',
    }
    status_descriptions = {
        'normal': 'Breathing activity within the local baseline range.',
        'underexerted': 'Low flex activity and motion.',
        'breath_hold': 'Sustained low flex activity across consecutive windows.',
        'rapid_breathing': 'Frequent flex oscillations consistent with rapid breathing.',
        'overexerted': 'High flex motion / possible labored breathing.',
    }
    alert_patches_axis2 = []
    alert_patches_axis3 = []

    for _, row in df_alerts.iterrows():
        start_ts = pd.to_datetime(row['start_ts']) if pd.notna(row['start_ts']) else None
        end_ts = pd.to_datetime(row['end_ts']) if pd.notna(row['end_ts']) else None
        if start_ts is None or end_ts is None:
            continue
        color = status_colors.get(row['status'], 'tab:gray')
        patch2 = axes[2].axvspan(start_ts, end_ts, color=color, alpha=0.18)
        patch2._hover_text = (
            f"Flex alert: {row['status']}\n"
            f"{status_descriptions.get(row['status'], 'No description available.')}\n"
            f"Reason: {row.get('notification', 'n/a')}\n"
            f"{start_ts} to {end_ts}"
        )
        alert_patches_axis2.append(patch2)

        patch3 = axes[3].axvspan(start_ts, end_ts, color=color, alpha=0.35)
        patch3._hover_text = (
            f"Flex alert: {row['status']}\n"
            f"{status_descriptions.get(row['status'], 'No description available.')}\n"
            f"Reason: {row.get('notification', 'n/a')}\n"
            f"{start_ts} to {end_ts}"
        )
        alert_patches_axis3.append(patch3)
        axes[3].text(start_ts, 0.5, row['status'], fontsize=8, rotation=0, va='center', ha='left', color='black')

    axes[2].legend(
        handles=[
            Patch(facecolor='tab:green', alpha=0.18, label='normal'),
            Patch(facecolor='tab:purple', alpha=0.18, label='underexerted'),
            Patch(facecolor='tab:red', alpha=0.18, label='breath_hold'),
            Patch(facecolor='tab:cyan', alpha=0.18, label='rapid_breathing'),
            Patch(facecolor='tab:orange', alpha=0.18, label='overexerted'),
        ],
        title='Flex alert colours',
        loc='upper right',
        fontsize=8,
    )
    axes[3].legend(
        handles=[
            Line2D([0], [0], color='tab:green', lw=1.8, label='Model prediction'),
            Line2D([0], [0], color='tab:red', lw=1.4, label='Flex alert state'),
            Patch(facecolor='tab:green', alpha=0.35, label='normal'),
            Patch(facecolor='tab:purple', alpha=0.35, label='underexerted'),
            Patch(facecolor='tab:red', alpha=0.35, label='breath_hold'),
            Patch(facecolor='tab:cyan', alpha=0.35, label='rapid_breathing'),
            Patch(facecolor='tab:orange', alpha=0.35, label='overexerted'),
        ],
        title='Timeline legend',
        loc='upper left',
        fontsize=8,
    )

    _attach_hover_tooltip(fig, axes[2], alert_patches_axis2)
    _attach_hover_tooltip(fig, axes[3], alert_patches_axis3)

    summary = df_alerts['status'].value_counts().to_dict() if not df_alerts.empty else {}
    print('\n--- Flex breathing alert summary ---')
    print(summary if summary else 'No flex alerts detected')

    plt.tight_layout()
    plt.show()


def main():
    parser = argparse.ArgumentParser(description='Visualise apnea predictions and flex-based breathing alerts')
    parser.add_argument('--mode', choices=['dataset', 'database'], default='database')
    parser.add_argument('--input_source', default='a04r')
    parser.add_argument('--db_source', default='latest')
    parser.add_argument('--minutes', type=int, default=None)
    parser.add_argument('--hours', type=int, default=None)
    parser.add_argument('--num_records', type=int, default=1200)
    args = parser.parse_args()

    if args.mode == 'dataset':
        plot_dataset_predictions(args.input_source)
    else:
        plot_database_flex_alerts(args.db_source, minutes=args.minutes, hours=args.hours, num_records=args.num_records)


if __name__ == '__main__':
    main()
    raise SystemExit(0)

# Run on a record the model HAS NOT seen (e.g., a04r)

# You can run the model on dataset data or on our custom sensor data. Both are shown below.

data = run_inference(mode='dataset', input_source='a04r')
#data = run_inference(mode='sensor', input_source='MAX_kevin_data.txt')

# Create a 3-panel plot
fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 10), sharex=True)

samples_per_min = int(len(data['spo2']) / len(data['actuals']))
time_mins = np.arange(len(data['actuals']))

# Plot 1: Raw SpO2 Signal
ax1.plot(data['spo2'], color='blue', alpha=0.6, label='Raw SpO2')
ax1.set_title("Apnea Analysis: Ground Truth vs Prediction")
ax1.set_ylabel("SpO2 %")

# Plot 2: Ground Truth (Doctor)
for i, act in enumerate(data['actuals']):
    ax2.axvspan(i*samples_per_min, (i+1)*samples_per_min, 
                color='green' if act==0 else 'red', alpha=0.3)
ax2.set_ylabel("Actual Label\n(Doctor)")
ax2.set_yticks([])

# Plot 3: Model Prediction
for i, pred in enumerate(data['preds']):
    ax3.axvspan(i*samples_per_min, (i+1)*samples_per_min, 
                color='green' if pred==0 else 'red', alpha=0.3)
ax3.set_ylabel("AI Prediction\n(Model)")
ax3.set_xlabel("Samples (Seconds if 1Hz)")

# Error Highlighting (Optional but helpful)
# We draw small markers where the model was WRONG
for i in range(len(data['preds'])):
    if data['preds'][i] != data['actuals'][i]:
        ax1.vlines(i*samples_per_min + (samples_per_min/2), 70, 100, 
                   color='orange', linestyles='dotted', alpha=0.5)

plt.tight_layout()
plt.show()

# Print the formal stats
print("\n--- Validation Statistics ---")
print(classification_report(data['actuals'], data['preds'], target_names=['Normal', 'Apnea']))