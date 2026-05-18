<?php
header('Content-Type: application/json');

// Increase max execution time for long-running inference calls
@ini_set('max_execution_time', '120');
@set_time_limit(120);

$python = '/Users/mudithapallewela/slumber/.venv/bin/python';
$script = __DIR__ . '/../Inferencing_Code/infer_api.py';

// Optional: allow time window via query
$minutes = isset($_GET['minutes']) ? intval($_GET['minutes']) : null;
$hours = isset($_GET['hours']) ? intval($_GET['hours']) : null;
$start = isset($_GET['start']) ? $_GET['start'] : null;
$end = isset($_GET['end']) ? $_GET['end'] : null;

// Adaptive window sizing based on time range
$timeMinutes = 0;
if ($minutes !== null && $minutes > 0) {
    $timeMinutes = $minutes;
} elseif ($hours !== null && $hours > 0) {
    $timeMinutes = $hours * 60;
}

$windowSeconds = 30;
$windowStrideSeconds = 15;

// For small time ranges, use smaller windows for faster processing
if ($timeMinutes > 0) {
    if ($timeMinutes <= 5) {
        $windowSeconds = 10;
        $windowStrideSeconds = 3;
    } elseif ($timeMinutes <= 10) {
        $windowSeconds = 12;
        $windowStrideSeconds = 4;
    } elseif ($timeMinutes <= 60) {
        $windowSeconds = 15;
        $windowStrideSeconds = 5;
    }
}

$cmdParts = [escapeshellcmd($python), escapeshellarg($script)];

if ($start !== null && $end !== null) {
    $cmdParts[] = '--start';
    $cmdParts[] = escapeshellarg($start);
    $cmdParts[] = '--end';
    $cmdParts[] = escapeshellarg($end);
} elseif ($minutes !== null && $minutes > 0) {
    $cmdParts[] = '--minutes';
    $cmdParts[] = escapeshellarg((string)$minutes);
} elseif ($hours !== null && $hours > 0) {
    $cmdParts[] = '--hours';
    $cmdParts[] = escapeshellarg((string)$hours);
} else {
    $cmdParts[] = '--hours';
    $cmdParts[] = '24';
}

// Add adaptive window parameters
$cmdParts[] = '--window_seconds';
$cmdParts[] = escapeshellarg((string)$windowSeconds);
$cmdParts[] = '--window_stride_seconds';
$cmdParts[] = escapeshellarg((string)$windowStrideSeconds);

$cmd = implode(' ', $cmdParts);

// Execute and capture output
exec($cmd . ' 2>&1', $output, $ret);

if ($ret !== 0) {
    http_response_code(500);
    echo json_encode(['error' => 'Inference failed', 'output' => implode("\n", $output)]);
    exit;
}

echo implode("\n", $output);
?>
