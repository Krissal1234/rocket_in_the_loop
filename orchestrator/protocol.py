import struct

SENSOR_STRUCT_FMT   = ">8d"          # > = big-endian, 8 doubles
SENSOR_STRUCT_SIZE  = struct.calcsize(SENSOR_STRUCT_FMT)   # 64 bytes
ACK_BYTE            = 0x06
