"""Shared DBC content strings used across the test suite."""

# All 7 required messages, no optional messages (DOORS / GENERAL_LIGHTS absent).
# Used in test_dbc.py to verify optional-message absence.
MINIMAL_DBC = """\
VERSION ""

NS_ :

BS_:

BU_: ECU

BO_ 1536 THROTTLE: 4 ECU
 SG_ THROTTLE_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1537 BRAKE: 4 ECU
 SG_ BRAKE_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1538 STEER: 4 ECU
 SG_ STEER_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1539 REVERSE: 1 ECU
 SG_ REVERSE_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1540 HAND_BRAKE: 1 ECU
 SG_ HAND_BRAKE_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1542 MANUAL_TRANSMISSION: 1 ECU
 SG_ MANUAL_TRANSMISSION_signal : 0|8@1+ (1,0) [0|255] "" ECU

BO_ 1543 GEAR: 4 ECU
 SG_ GEAR_signal : 0|8@1+ (1,0) [0|255] "" ECU

BA_DEF_ BO_ "GenMsgCycleTime" INT 0 10000;

BA_DEF_DEF_ "GenMsgCycleTime" 0;

BA_ "GenMsgCycleTime" BO_ 1536 100;
BA_ "GenMsgCycleTime" BO_ 1537 100;
BA_ "GenMsgCycleTime" BO_ 1538 100;
BA_ "GenMsgCycleTime" BO_ 1539 200;
BA_ "GenMsgCycleTime" BO_ 1540 200;
BA_ "GenMsgCycleTime" BO_ 1542 500;
BA_ "GenMsgCycleTime" BO_ 1543 200;

"""

# All 7 required messages plus the optional GENERAL_LIGHTS message (11 × 1-bit signals).
# Used in test_network_encoding.py which tests the lights encoding logic.
FULL_DBC = MINIMAL_DBC.replace(
    'BA_ "GenMsgCycleTime" BO_ 1543 200;\n',
    'BA_ "GenMsgCycleTime" BO_ 1543 200;\n'
    '\nBO_ 1549 GENERAL_LIGHTS: 2 ECU\n'
    ' SG_ LIGHTS_Position_signal     : 0|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_LowBeam_signal      : 1|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_HighBeam_signal     : 2|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Brake_signal        : 3|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_RightBlinker_signal : 4|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_LeftBlinker_signal  : 5|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Reverse_signal      : 6|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Fog_signal          : 7|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Interior_signal     : 8|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Special1_signal     : 9|1@1+  (1,0) [0|1] "" ECU\n'
    ' SG_ LIGHTS_Special2_signal     : 10|1@1+ (1,0) [0|1] "" ECU\n'
    '\nBA_ "GenMsgCycleTime" BO_ 1549 0;\n',
)

# FULL_DBC extended with all 6 sensor messages. Used in sensor encoding tests.
SENSOR_DBC = FULL_DBC.replace(
    'BA_ "GenMsgCycleTime" BO_ 1549 0;\n',
    'BA_ "GenMsgCycleTime" BO_ 1549 0;\n'
    '\nBO_ 1550 GNSS: 8 ECU\n'
    ' SG_ GNSS_LAT_signal : 0|32@1- (0.0000001,0) [-90|90] "deg" ECU\n'
    ' SG_ GNSS_LON_signal : 32|32@1- (0.0000001,0) [-180|180] "deg" ECU\n'
    '\nBO_ 1551 COLLISION: 2 ECU\n'
    ' SG_ COLLISION_INTENSITY_signal : 0|16@1+ (0.1,0) [0|6553.5] "" ECU\n'
    '\nBO_ 1552 LANE_INVASION: 2 ECU\n'
    ' SG_ LANE_INVASION_TYPE_signal : 0|16@1+ (1,0) [0|65535] "" ECU\n'
    '\nBO_ 1553 IMU_ACCEL: 6 ECU\n'
    ' SG_ IMU_ACCEL_X_signal : 0|16@1- (0.01,0) [-327.68|327.67] "m/s2" ECU\n'
    ' SG_ IMU_ACCEL_Y_signal : 16|16@1- (0.01,0) [-327.68|327.67] "m/s2" ECU\n'
    ' SG_ IMU_ACCEL_Z_signal : 32|16@1- (0.01,0) [-327.68|327.67] "m/s2" ECU\n'
    '\nBO_ 1554 IMU_GYRO: 6 ECU\n'
    ' SG_ IMU_GYRO_X_signal : 0|16@1- (0.01,0) [-327.68|327.67] "deg/s" ECU\n'
    ' SG_ IMU_GYRO_Y_signal : 16|16@1- (0.01,0) [-327.68|327.67] "deg/s" ECU\n'
    ' SG_ IMU_GYRO_Z_signal : 32|16@1- (0.01,0) [-327.68|327.67] "deg/s" ECU\n'
    '\nBO_ 1555 IMU_COMPASS: 2 ECU\n'
    ' SG_ IMU_COMPASS_signal : 0|16@1+ (0.01,0) [0|655.35] "deg" ECU\n'
    '\nBA_ "GenMsgCycleTime" BO_ 1550 1000;\n'
    'BA_ "GenMsgCycleTime" BO_ 1551 0;\n'
    'BA_ "GenMsgCycleTime" BO_ 1552 0;\n'
    'BA_ "GenMsgCycleTime" BO_ 1553 100;\n'
    'BA_ "GenMsgCycleTime" BO_ 1554 100;\n'
    'BA_ "GenMsgCycleTime" BO_ 1555 100;\n'
    '\nBO_ 1556 RADAR_TARGET: 8 ECU\n'
    ' SG_ RADAR_VEL_signal : 0|16@1- (0.01,0) [-327.68|327.67] "m/s" ECU\n'
    ' SG_ RADAR_AZI_signal : 16|16@1- (0.01,0) [-327.68|327.67] "deg" ECU\n'
    ' SG_ RADAR_ALT_signal : 32|16@1- (0.01,0) [-327.68|327.67] "deg" ECU\n'
    ' SG_ RADAR_DEPTH_signal : 48|16@1+ (0.01,0) [0|655.35] "m" ECU\n'
    '\nBA_ "GenMsgCycleTime" BO_ 1556 0;\n',
)
