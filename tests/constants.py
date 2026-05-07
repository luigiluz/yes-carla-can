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

# All 7 required messages plus the optional GENERAL_LIGHTS message.
# Used in test_network_encoding.py which tests the lights-mask logic.
FULL_DBC = MINIMAL_DBC.replace(
    'BA_ "GenMsgCycleTime" BO_ 1543 200;\n',
    'BA_ "GenMsgCycleTime" BO_ 1543 200;\n'
    '\nBO_ 1549 GENERAL_LIGHTS: 4 ECU\n'
    ' SG_ GENERAL_LIGHTS_signal : 0|8@1+ (1,0) [0|255] "" ECU\n'
    '\nBA_ "GenMsgCycleTime" BO_ 1549 0;\n',
)
