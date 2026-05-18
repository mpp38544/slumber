import argparse
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd
from updated_inference import detect_flex_breathing_alerts, infer_from_db, load_from_database
from matplotlib.lines import Line2D
from matplotlib.patches import Patch


def _status_to_level(status):
    return {
        'normal': 0,
        'underexerted': 1,
        'breath_hold': 2,
        'rapid_breathing': 3,
        'overexerted': 4,
    }.get(status, 0)


def _build_minute_timeline(df_inf, df_alerts, start_ts, end_ts):
    minute_index = pd.date_range(start=start_ts.floor('min'), end=end_ts.ceil('min'), freq='1min')
    prediction_series = pd.Series(index=minute_index, dtype=float)
    alert_series = pd.Series(index=minute_index, dtype=float)

    if df_inf is not None and not df_inf.empty:
        pred_minutes = df_inf['end_ts'].dt.floor('min')
        pred_values = df_inf['pred'].astype(float).values
        pred_frame = pd.DataFrame({'minute': pred_minutes, 'pred': pred_values}).groupby('minute')['pred'].max()
        prediction_series.loc[pred_frame.index] = pred_frame.values

    if df_alerts is not None and not df_alerts.empty:
        alert_minutes = df_alerts['end_ts'].dt.floor('min')
        alert_levels = df_alerts['status'].map(_status_to_level).astype(float).values
        alert_frame = pd.DataFrame({'minute': alert_minutes, 'alert': alert_levels}).groupby('minute')['alert'].max()
        alert_series.loc[alert_frame.index] = alert_frame.values

    return minute_index, prediction_series, alert_series


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


def plot_raw_and_inference(db_source='hours', num_records=1200, hours=24, save_png=None, window_seconds=30, window_stride_seconds=15, sensitivity_offset=0.15):
    hr, spo2, flex, timestamps = load_from_database(
        db_source=db_source,
        num_records=num_records,
        hours=hours,
        include_flex=True,
    )

    # Build DataFrame for raw signals
    df_raw = pd.DataFrame({
        'timestamp': pd.to_datetime(timestamps),
        'hr': hr,
        'spo2': spo2,
        'flex_voltage': flex
    })

    # Run inference aggregated per minute
    df_inf = infer_from_db(db_source=db_source, num_records=num_records, hours=hours)
    if not df_inf.empty:
        df_inf['end_ts'] = pd.to_datetime(df_inf['end_ts'])
        df_inf['start_ts'] = pd.to_datetime(df_inf['start_ts'])

    df_alerts = detect_flex_breathing_alerts(
        flex,
        timestamps=timestamps,
        window_seconds=window_seconds,
        window_stride_seconds=window_stride_seconds,
        sensitivity_offset=sensitivity_offset,
    )
    if not df_alerts.empty:
        df_alerts['start_ts'] = pd.to_datetime(df_alerts['start_ts'])
        df_alerts['end_ts'] = pd.to_datetime(df_alerts['end_ts'])

    # Plot
    fig, axes = plt.subplots(4, 1, figsize=(16, 12), sharex=True)
    time_index = pd.to_datetime(timestamps)
    model_span_patches = []
    flex_span_patches = []

    axes[0].plot(df_raw['timestamp'], df_raw['hr'], color='tab:red', linewidth=1.1)
    axes[0].set_ylabel('HR (BPM)')
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(df_raw['timestamp'], df_raw['spo2'], color='tab:blue', linewidth=1.1)
    axes[1].set_ylabel('SpO2 (%)')
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(df_raw['timestamp'], df_raw['flex_voltage'], color='tab:orange', linewidth=1.1)
    axes[2].set_ylabel('Flex Voltage (V)')
    axes[2].grid(True, alpha=0.3)

    if not df_alerts.empty:
        for _, row in df_alerts.iterrows():
            color = {
                'underexerted': 'tab:purple',
                'breath_hold': 'tab:red',
                'rapid_breathing': 'tab:cyan',
                'overexerted': 'tab:red',
                'normal': 'tab:green'
            }.get(row['status'], 'tab:gray')
            if pd.notna(row['start_ts']) and pd.notna(row['end_ts']):
                patch = axes[2].axvspan(row['start_ts'], row['end_ts'], color=color, alpha=0.16)
                patch._hover_text = (
                    f"Flex alert: {row['status']}\n"
                    f"Reason: {row.get('notification', 'n/a')}\n"
                    f"{row['start_ts']} to {row['end_ts']}"
                )
                flex_span_patches.append(patch)

    # Timeline panel: actual graph for the last-day analysis
    alert_levels = {
        'normal': 0,
        'underexerted': 1,
        'breath_hold': 2,
        'rapid_breathing': 3,
        'overexerted': 4,
    }
    alert_colors = {
        'normal': 'tab:green',
        'underexerted': 'tab:purple',
        'breath_hold': 'tab:red',
        'rapid_breathing': 'tab:cyan',
        'overexerted': 'tab:orange',
    }
    axes[3].set_title('Last day analysis timeline')
    axes[3].set_ylabel('State')
    axes[3].set_ylim(-0.4, 4.4)
    axes[3].set_yticks([0, 1, 2, 3, 4])
    axes[3].set_yticklabels(['normal', 'underexerted', 'breath_hold', 'rapid_breathing', 'overexerted'])
    axes[3].grid(True, axis='x', alpha=0.2)
    axes[3].grid(True, axis='y', alpha=0.15)

    if not df_raw.empty:
        minute_index, prediction_series, alert_series = _build_minute_timeline(df_inf, df_alerts, df_raw['timestamp'].min(), df_raw['timestamp'].max())
        pred_line = prediction_series.ffill().fillna(0.0)
        alert_line = alert_series.ffill().fillna(0.0)

        axes[3].step(minute_index, pred_line, where='post', color='tab:green', linewidth=1.8, label='Apnea model prediction')
        axes[3].scatter(minute_index, pred_line, c=pred_line.map({0.0: 'tab:green', 1.0: 'tab:red'}), s=14, alpha=0.8)

        axes[3].step(minute_index, alert_line, where='post', color='tab:red', linewidth=1.4, alpha=0.9, label='Flex alert state')
        axes[3].scatter(minute_index, alert_line, c=alert_line.map({0.0: 'tab:green', 1.0: 'tab:purple', 2.0: 'tab:red', 3.0: 'tab:cyan', 4.0: 'tab:orange'}), s=12, alpha=0.8)

        axes[3].xaxis_date()
        axes[3].xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
        axes[3].tick_params(axis='x', rotation=25)
        axes[3].legend(loc='upper left', fontsize=8)

    if not df_inf.empty:
        for _, row in df_inf.iterrows():
            start_ts = pd.to_datetime(row['start_ts']) if pd.notna(row['start_ts']) else None
            end_ts = pd.to_datetime(row['end_ts']) if pd.notna(row['end_ts']) else None
            if start_ts is None or end_ts is None:
                continue
            color = 'tab:red' if int(row['pred']) == 1 else 'tab:green'
            for ax in axes[:2]:
                patch = ax.axvspan(start_ts, end_ts, color=color, alpha=0.08)
                patch._hover_text = f"Model prediction: {'Apnea' if int(row['pred']) == 1 else 'Normal'}\n{start_ts} to {end_ts}"
                model_span_patches.append((ax, patch))

    axes[0].legend(handles=[Line2D([0], [0], color='tab:red', lw=1.1, label='HR trace')], loc='upper right', fontsize=8)
    axes[1].legend(handles=[Line2D([0], [0], color='tab:blue', lw=1.1, label='SpO2 trace')], loc='upper right', fontsize=8)
    axes[2].legend(
        handles=[
            Patch(facecolor='tab:green', alpha=0.16, label='normal'),
            Patch(facecolor='tab:purple', alpha=0.16, label='underexerted'),
            Patch(facecolor='tab:red', alpha=0.16, label='breath_hold'),
            Patch(facecolor='tab:cyan', alpha=0.16, label='rapid_breathing'),
            Patch(facecolor='tab:orange', alpha=0.16, label='overexerted'),
        ],
        title='Flex alert colours',
        loc='upper right',
        fontsize=8,
    )
    axes[3].legend(
        handles=[
            Line2D([0], [0], color='tab:green', lw=1.8, label='Apnea model prediction'),
            Line2D([0], [0], color='tab:red', lw=1.4, label='Flex alert state'),
            Patch(facecolor='tab:cyan', alpha=0.35, label='rapid_breathing'),
        ],
        loc='upper left',
        fontsize=8,
    )

    _attach_hover_tooltip(fig, axes[2], flex_span_patches)
    _attach_hover_tooltip(fig, axes[0], [patch for ax, patch in model_span_patches if ax == axes[0]])
    _attach_hover_tooltip(fig, axes[1], [patch for ax, patch in model_span_patches if ax == axes[1]])

    # Overlay predictions as markers on HR plot (if available)
    if not df_inf.empty:
        axes[0].scatter(df_inf['end_ts'], [df_raw['hr'].iloc[0]] * len(df_inf),
                        c=df_inf['pred'].map({0: 'green', 1: 'red'}),
                        marker='x', label='pred')
        axes[0].legend()

    if not df_alerts.empty:
        alert_counts = df_alerts['status'].value_counts().to_dict()
        print('\n--- Flex breathing alerts ---')
        print(alert_counts)

    plt.xlabel('Time')
    plt.tight_layout()

    if save_png:
        fig.savefig(save_png)
        print(f"Saved plot to {save_png}")
    else:
        plt.show()


def main():
    p = argparse.ArgumentParser(description='Plot vitals from DB and inference results')
    p.add_argument('--db_source', default='hours')
    p.add_argument('--num_records', type=int, default=1200)
    p.add_argument('--hours', type=int, default=24)
    p.add_argument('--save', default=None, help='Path to save PNG (optional)')
    p.add_argument('--window_seconds', type=int, default=8)
    p.add_argument('--window_stride_seconds', type=int, default=3)
    p.add_argument('--sensitivity_offset', type=float, default=0.15)
    args = p.parse_args()

    plot_raw_and_inference(
        args.db_source,
        args.num_records,
        args.hours,
        args.save,
        window_seconds=args.window_seconds,
        window_stride_seconds=args.window_stride_seconds,
        sensitivity_offset=args.sensitivity_offset,
    )


if __name__ == '__main__':
    main()