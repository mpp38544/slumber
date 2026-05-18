<?php
header('Content-Type: application/json');

$python = '/Users/mudithapallewela/slumber/.venv/bin/python';
$script = __DIR__ . '/../Inferencing_Code/infer_api.py';

// Optional: allow time window via query
$minutes = isset($_GET['minutes']) ? intval($_GET['minutes']) : null;
$hours = isset($_GET['hours']) ? intval($_GET['hours']) : null;

$cmdParts = [escapeshellcmd($python), escapeshellarg($script)];

if ($minutes !== null && $minutes > 0) {
    $cmdParts[] = '--minutes';
    $cmdParts[] = escapeshellarg((string)$minutes);
} elseif ($hours !== null && $hours > 0) {
    $cmdParts[] = '--hours';
    $cmdParts[] = escapeshellarg((string)$hours);
} else {
    $cmdParts[] = '--hours';
    $cmdParts[] = '24';
}

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
