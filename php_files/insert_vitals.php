<?php
$server   = "localhost";
$user     = "root";
$password = "";
$database = "db_health";

$conn = mysqli_connect($server, $user, $password, $database);
if (!$conn) {
    die("Connection failed");
}

$hr   = $_POST['hr'];
$spo2 = $_POST['spo2'];
$flex = $_POST['flex'];

$sql = "INSERT INTO tbl_vitals (hr, spo2, flex_voltage) VALUES ('$hr', '$spo2', '$flex')";
// Keep only last 10 minutes
$conn->query("DELETE FROM tbl_vitals WHERE created_at < NOW() - INTERVAL 10 MINUTE");

if (mysqli_query($conn, $sql)) {
    echo "Data inserted successfully";
} else {
    echo "Error: " . mysqli_error($conn);
}

mysqli_close($conn);
?>