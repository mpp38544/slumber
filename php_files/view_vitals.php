<?php
$server   = "localhost";
$user     = "root";
$password = "";
$database = "db_health";

$conn = mysqli_connect($server, $user, $password, $database);
if (!$conn) {
    die("Connection failed");
}

$sql    = "SELECT * FROM tbl_vitals ORDER BY created_at DESC";
$result = mysqli_query($conn, $sql);

echo "<html><body>";
echo "<h1>Health Vitals</h1>";
echo "<table border='1'><tr><th>HR</th><th>SpO2</th><th>Flex Voltage</th><th>Time</th></tr>";

while ($row = mysqli_fetch_assoc($result)) {
    echo "<tr>
            <td>" . $row['hr'] . "</td>
            <td>" . $row['spo2'] . "</td>
            <td>" . $row['flex_voltage'] . "</td>
            <td>" . $row['created_at'] . "</td>
          </tr>";
}

echo "</table></body></html>";
mysqli_close($conn);
?>