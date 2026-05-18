<?php
header('Content-Type: application/json');

$server   = "localhost";
$user     = "root";
$password = "";
$database = "db_health";

$conn = mysqli_connect($server, $user, $password, $database);
if (!$conn) {
    die(json_encode(['error' => 'Connection failed']));
}

$minutes = isset($_GET['minutes']) ? intval($_GET['minutes']) : null;
$hours = isset($_GET['hours']) ? intval($_GET['hours']) : null;

if ($minutes !== null && $minutes > 0) {
    $sql = "SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL $minutes MINUTE) 
            ORDER BY created_at ASC";
} elseif ($hours !== null && $hours > 0) {
    $sql = "SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL $hours HOUR) 
            ORDER BY created_at ASC";
} else {
    // Default to the last 24 hours
    $sql = "SELECT hr, spo2, flex_voltage, created_at FROM tbl_vitals 
            WHERE created_at >= DATE_SUB(NOW(), INTERVAL 24 HOUR) 
            ORDER BY created_at ASC";
}

$result = mysqli_query($conn, $sql);

if (!$result) {
    die(json_encode(['error' => mysqli_error($conn)]));
}

$data = array(
    'created_ats' => array(),
    'hr' => array(),
    'spo2' => array(),
    'flex_voltage' => array()
);

while ($row = mysqli_fetch_assoc($result)) {
    $data['created_ats'][] = $row['created_at'];
    $data['hr'][] = (int)$row['hr'];
    $data['spo2'][] = (int)$row['spo2'];
    $data['flex_voltage'][] = (float)$row['flex_voltage'];
}

mysqli_close($conn);

echo json_encode($data);
?>
