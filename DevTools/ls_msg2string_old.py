import logging as _logging
import math as _math
import struct as _struct

import ls_message_parsing

ls_message_parsing.SHOW_HIDDEN_FIELDS = True
import json as _json
from ast import literal_eval
from re import sub as _sub

# import numpy
#import generic_modbus_cfgs as gmcfgs
from ls_message_parsing.ls_message_parsing import decode_msg as _decode_msg
from ls_message_parsing.utils.time_utils import second_to_time_iso8601 as _second_to_time_iso8601

# Global variables
PRCODE = 0
NODEID = 0

# timestamp 4, pressure 2, [0..5] * (channel 1, freq 3, thermistor 4) -> sizes: 6, 14, 22, 30, 38, 46
def _get_vw_magnitude_data_str(msg):
    msg_len = len(msg)
    if 0 == msg_len:
        unpack_format = "!"
        num_channels = 0
    elif 8 == msg_len:
        unpack_format = "!BBHf"
        num_channels = 1
    elif 16 == msg_len:
        unpack_format = "!BBHfBBHf"
        num_channels = 2
    elif 24 == msg_len:
        unpack_format = "!BBHfBBHfBBHf"
        num_channels = 3
    elif 32 == msg_len:
        unpack_format = "!BBHfBBHfBBHfBBHf"
        num_channels = 4
    elif 40 == msg_len:
        unpack_format = "!BBHfBBHfBBHfBBHfBBHf"
        num_channels = 5

    vw_data_str = ""

    unp_msg = _struct.unpack(unpack_format, msg)
    for i in range(0, num_channels):
        vw_data_str += "; Ch: " + "%u" % (unp_msg[4 * i])
        frequency = (unp_msg[4 * i + 1] << 16) | unp_msg[4 * i + 2]
        vw_data_str += " [Freq: "
        vw_data_str += str(frequency)
        vw_data_str += "; Magnitude: " + "%f]" % (unp_msg[4 * i + 3])

    return vw_data_str


# timestamp 4, pressure 2, [0..5] * (channel 1, freq 3, thermistor 4) -> sizes: 6, 14, 22, 30, 38, 46
def _get_vw_data_str(msg):
    vw_freq_error_value = (2 ** 24) - 1
    msg_len = len(msg)
    if 6 == msg_len:
        unpack_format = "!IH"
        num_channels = 0
    elif 14 == msg_len:
        unpack_format = "!IHBBHI"
        num_channels = 1
    elif 22 == msg_len:
        unpack_format = "!IHBBHIBBHI"
        num_channels = 2
    elif 30 == msg_len:
        unpack_format = "!IHBBHIBBHIBBHI"
        num_channels = 3
    elif 38 == msg_len:
        unpack_format = "!IHBBHIBBHIBBHIBBHI"
        num_channels = 4
    elif 46 == msg_len:
        unpack_format = "!IHBBHIBBHIBBHIBBHIBBHI"
        num_channels = 5

    unp_msg = _struct.unpack(unpack_format, msg)
    vw_data_str = "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    vw_data_str += "; Pressure: " + "%u" % (unp_msg[1])
    for i in range(0, num_channels):
        vw_data_str += "; Ch: " + "%u" % (unp_msg[4 * i + 2])
        frequency = (unp_msg[4 * i + 1 + 2] << 16) | unp_msg[4 * i + 2 + 2]
        vw_data_str += " [Freq: "
        vw_data_str += str(frequency) if frequency != vw_freq_error_value else "NoSensor"
        vw_data_str += "; Therm: " + "%u]" % (unp_msg[4 * i + 3 + 2])

    return vw_data_str


def _get_vw_config_str(msg):
    unp_msg = _struct.unpack("!BHBBBBBBHHH", msg)
    sampling_period = (unp_msg[0] << 16) | unp_msg[1]
    vw_config_str = "; SamplingPeriod: " + str(sampling_period)
    vw_config_str += "; ChEnBitmap: " + "%x" % (unp_msg[2])
    vw_config_str += "; Sweep Type: [%x,%x,%x,%x,%x]" % (
        unp_msg[3],
        unp_msg[4],
        unp_msg[5],
        unp_msg[6],
        unp_msg[7],
    )
    vw_config_str += "; Sweep Custom: [%u,%u,%u]" % (unp_msg[8], unp_msg[9], unp_msg[10])
    return vw_config_str


def _create_mask(num_bits):
    return (1 << num_bits) - 1


def _extract_bits_from_array(msg, bit_offset, num_bits):
    first_byte = bit_offset // 8
    first_bit_offset = bit_offset % 8
    last_byte = (bit_offset + num_bits - 1) // 8
    last_bit_offset = (bit_offset + num_bits - 1) % 8

    value = 0

    current_mask_size = 8 - first_bit_offset
    current_mask = _create_mask(current_mask_size)

    current_byte = first_byte
    while current_byte < last_byte:
        byte = _struct.unpack("!B", msg[current_byte : current_byte + 1])
        value = (value << current_mask_size) | (current_mask & byte[0])

        current_mask_size = 8
        current_mask = _create_mask(current_mask_size)
        current_byte = current_byte + 1

    discard_right_numbits = 8 - (last_bit_offset + 1)

    current_mask_size = current_mask_size - discard_right_numbits
    current_mask = _create_mask(current_mask_size)

    byte = _struct.unpack("!B", msg[current_byte : current_byte + 1])
    value = (value << current_mask_size) | (current_mask & (byte[0] >> discard_right_numbits))

    return value


def _uint_to_int(val, num_bits):

    sign_bit_mask = 1 << (num_bits - 1)
    if 0 != (sign_bit_mask & val):
        val_mask = _create_mask(num_bits - 1)
        # remove sign bit
        val = val & val_mask
        # xor the value with the mask to invert the bits and add 1
        ret_val = ((val_mask ^ val) + 1) * -1
    else:
        ret_val = val
    return ret_val


def _uint_to_float(val):
    return _struct.unpack("f", _struct.pack("I", val))[0]


def _is_out_of_range(is_signed, num_bits, raw_value):

    if is_signed:
        check = 1 << (num_bits - 1)

    else:
        check = (1 << (num_bits)) - 1

    return raw_value == check


#def _get_gm_data_str(msg):

#    msg_hdr = _struct.unpack("!IH", msg[:6])
#    gm_data_str = "; Time: %u (%s)" % (msg_hdr[0], _second_to_time_iso8601(msg_hdr[0]))

    # Config ID field
#    config_id = msg_hdr[1]
#    gm_data_str += "; Config ID: %u" % config_id

    # Get Frame Header
#    bitoffset = 0
#    frame_number = _extract_bits_from_array(msg[6:], bitoffset, 4)
#    bitoffset += 4
#    total_sensors = _extract_bits_from_array(msg[6:], bitoffset, 6)
#    bitoffset += 6
#    sensors_in_msg = _extract_bits_from_array(msg[6:], bitoffset, 6)
#    bitoffset += 6
#    gm_data_str += "; Frame Num: %u; Total Sensors: %u; Num Sensors: %u;" % (
#        frame_number,
#        total_sensors,
#        sensors_in_msg,
#    )

 #   bitoffset = 0
 #   if total_sensors > 0:
        # Init the object
#        gm_cfgs_obj = gmcfgs.GenericModbusDataCfgs(config_id)

#        if gm_cfgs_obj.is_valid_cfg:
#            sensors_per_frame = gm_cfgs_obj.get_sensors_per_frame()
            # Check if is eod
#            eod = (
#                1
#                if (
#                    ((frame_number * sensors_per_frame) - (sensors_per_frame - sensors_in_msg))
#                    == total_sensors
#                )
#                else 0
#            )
#            gm_data_str += " EOD %u;" % (eod)

#            for i in range(0, sensors_in_msg):
#                num_sensor = (sensors_per_frame * (frame_number - 1)) + (i + 1)
#                gm_data_str += " Sensor %u " % (num_sensor) + " "

                # Sensor error bit
#                error_bit = _extract_bits_from_array(msg[8:], bitoffset, 1)
#                bitoffset += 1

#                if error_bit == 0:
                    # Sensor data
#                    channel = 0
#                    for chn in gm_cfgs_obj.channels_info:
#                        channel += 1
#                        value = _extract_bits_from_array(msg[8:], bitoffset, chn["data_size"])
#                        bitoffset += chn["data_size"]

#                        if _is_out_of_range(chn["signed_value"], chn["data_size"], value):
#                            value = "OutOfRange"
#                            gm_data_str += chn["label"] + ": " + str(value) + ", "
#                        else:
#                            if chn["signed_value"]:
#                                value = _uint_to_int(value, chn["data_size"])

#                            if chn["data_conversion"]:
#                                if chn["conversion_func_python"] == "":
#                                    warning_message = "No conversion function, RAW data: "
#                                    value = warning_message + str(value)
#                                else:
#                                    func = eval(chn["conversion_func_python"])
#                                    value = func(value)

#                            gm_data_str += (
#                                chn["label"] + ": " + str(value) + " " + chn["unit"] + ", "
#                            )
#                else:
#                    gm_data_str += " No response"

#                gm_data_str += ";"
#        else:
#            gm_data_str += (
#                " Parsing error: The configuration to parse this message was not found!!!!"
#            )
#    else:
#        gm_data_str += " General error: "
        # Reserved
#        _extract_bits_from_array(msg[8:], bitoffset, 2)
#        bitoffset += 2
#        error_code = _extract_bits_from_array(msg[8:], bitoffset, 4)
#        bitoffset += 4
#        error_param = _extract_bits_from_array(msg[8:], bitoffset, 10)
#        bitoffset += 10
#        gm_data_str += "Code: %u, Parameter: %u" % (error_code, error_param)

#    return gm_data_str


# 1 -> protocol & num channels; 2-177 -> ids of the channels.
# Sizes: 6, 9, 13, 16, 20, 23, 27, 30, 34, 37, 41, 44, 48, 51, 55, 58, 62, 65, 69, 72, 76, 79, 83, 86, 90, 93, 97,
# 100, 104, 107, 111, 114, 118, 121, 125, 128, 132, 135, 139, 142, 146, 149, 153, 156, 160, 163, 167, 170, 174, 177
def _get_gsi_data_str(msg):
    msg_hdr = _struct.unpack("!IB", msg[:5])
    gsi_data_str = "; Time: %u (%s)" % (msg_hdr[0], _second_to_time_iso8601(msg_hdr[0]))
    gsi_data_str += "; EOD: " + "%u" % ((msg_hdr[1] & 0x80) >> 7)
    num_channels = (msg_hdr[1] & 0x70) >> 4
    gsi_data_str += "; NumCh: " + "%u" % (num_channels)
    gsi_data_str += "; NumMsg: " + "%u" % (msg_hdr[1] & 0x0F)

    bitoffset = 0

    for i in range(0, num_channels):
        num_axis = (_extract_bits_from_array(msg[5:], bitoffset, 1)) + 1
        gsi_data_str += "; Ch %u: Axis = %u" % (i, num_axis)
        bitoffset = bitoffset + 1

        temp = _extract_bits_from_array(msg[5:], bitoffset, 11)
        if 0x400 != temp:
            gsi_data_str += ", Temp = %3.1f" % (float(_uint_to_int(temp, 11)) / 10.0)
        else:
            gsi_data_str += ", Temp = NaN"
        bitoffset = bitoffset + 11

        axe = _extract_bits_from_array(msg[5:], bitoffset, 19)
        if 0x40000 != axe:
            gsi_data_str += ", Axe1 = %2.4f" % (float(_uint_to_int(axe, 19)) / 10000.0)
        else:
            gsi_data_str += ", Axe1 = NaN"
        bitoffset = bitoffset + 19

        if 2 == num_axis:
            axe = _extract_bits_from_array(msg[5:], bitoffset, 19)
            if 0x40000 != axe:
                gsi_data_str += ", Axe2 = %2.4f" % (float(_uint_to_int(axe, 19)) / 10000.0)
            else:
                gsi_data_str += ", Axe2 = NaN"
            bitoffset = bitoffset + 19
        else:
            bitoffset = bitoffset + 1

    return gsi_data_str


def _get_dig_data_str(msg):
    msg_hdr = _struct.unpack("!IB", msg[:5])
    dig_data_str = "; Time: %u (%s)" % (msg_hdr[0], _second_to_time_iso8601(msg_hdr[0]))
    if msg_hdr[1] == 0:
        dig_data_str += "; GSI"
        dig_data_str += _get_dig_gsi_data_str(msg[5:])
    elif msg_hdr[1] == 1:
        dig_data_str += "; 6GEO Legacy"
        dig_data_str += _get_dig_6geo_legacy_data_str(msg[5:])
    elif msg_hdr[1] == 2:
        dig_data_str += "; MDT"
        dig_data_str += _get_dig_mdt_data_str(msg[5:])
    elif msg_hdr[1] == 3:
        dig_data_str += "; 6GEO V3"
        dig_data_str += _get_dig_6geo_v3_data_str(msg[5:])
    elif msg_hdr[1] == 4:
        dig_data_str += "; GeoFlex"
        dig_data_str += _get_dig_geoflex_data_str(msg[5:])
    elif msg_hdr[1] == 6:
        dig_data_str += "; Measurand SAAV"
        dig_data_str += _get_dig_measurand_data_str(msg[5:])
    elif msg_hdr[1] == 7:
        dig_data_str += "; YieldPoint"
        dig_data_str += _get_dig_yieldpoint_data_str(msg[5:])
    else:
        dig_data_str += "; Unknown sensor type (%u)" % (msg_hdr[1])

    return dig_data_str


# 1 -> protocol & num channels; 2-177 -> ids of the channels.
# Sizes: 6, 9, 13, 16, 20, 23, 27, 30, 34, 37, 41, 44, 48, 51, 55, 58, 62, 65, 69, 72, 76, 79, 83, 86, 90, 93, 97,
# 100, 104, 107, 111, 114, 118, 121, 125, 128, 132, 135, 139, 142, 146, 149, 153, 156, 160, 163, 167, 170, 174, 177
def _get_dig_gsi_data_str(msg):
    msg_hdr = _struct.unpack("!B", msg[:1])

    gsi_data_str = "; EOD: " + "%u" % ((msg_hdr[0] & 0x80) >> 7)
    num_channels = (msg_hdr[0] & 0x70) >> 4
    gsi_data_str += "; NumCh: " + "%u" % (num_channels)
    gsi_data_str += "; NumMsg: " + "%u" % (msg_hdr[0] & 0x0F)

    bitoffset = 0

    for i in range(0, num_channels):
        num_axis = (_extract_bits_from_array(msg[1:], bitoffset, 1)) + 1
        gsi_data_str += "; Ch %u: Axis = %u" % (i, num_axis)
        bitoffset = bitoffset + 1

        temp = _extract_bits_from_array(msg[1:], bitoffset, 11)
        if 0x400 != temp:
            gsi_data_str += ", Temp = %3.1f" % (float(_uint_to_int(temp, 11)) / 10.0)
        else:
            gsi_data_str += ", Temp = NaN"
        bitoffset = bitoffset + 11

        axe = _extract_bits_from_array(msg[1:], bitoffset, 19)
        if 0x40000 != axe:
            gsi_data_str += ", Axe1 = %2.4f" % (float(_uint_to_int(axe, 19)) / 10000.0)
        else:
            gsi_data_str += ", Axe1 = NaN"
        bitoffset = bitoffset + 19

        if 2 == num_axis:
            axe = _extract_bits_from_array(msg[1:], bitoffset, 19)
            if 0x40000 != axe:
                gsi_data_str += ", Axe2 = %2.4f" % (float(_uint_to_int(axe, 19)) / 10000.0)
            else:
                gsi_data_str += ", Axe2 = NaN"
            bitoffset = bitoffset + 19
        else:
            bitoffset = bitoffset + 1

    return gsi_data_str


def _get_geoflex_axis_value_or_error(value):
    error_range_start = 1000.01
    error_range_end = 1000.99

    error_switcher = {
        1000.01: "No response",
        1000.02: "Axis out of range",
        1000.03: "Chn not present",
        1000.04: "Invalid data",
        1000.05: "Sensor reported an error",
        1000.06: "Unexpected data format",
        1000.99: "Unknown error",
    }

    if value >= error_range_start and value <= error_range_end:
        return error_switcher.get(value, "Unrecognized error")
    else:
        return value


def _get_geoflex_axis_readings(chn_bitmask, combined_data):
    combine_factor = 200100
    combine_offset = 100000

    axis_x_mask = 0x04
    axis_x_shift = 2
    axis_y_mask = 0x02
    axis_y_shift = 1
    axis_z_mask = 0x01

    channels = []
    if (chn_bitmask & axis_x_mask) >> axis_x_shift:
        channels.insert(0, "Chn X")

    if (chn_bitmask & axis_y_mask) >> axis_y_shift:
        channels.insert(0, "Chn Y")

    if chn_bitmask & axis_z_mask:
        channels.insert(0, "Chn Z")

    recovered_other_channels = {}
    for i in range(0, len(channels)):
        if i == 0:
            recovered_other_channels[i] = combined_data
        else:
            recovered_other_channels[i] = recovered_other_channels[i - 1] / combine_factor

    # We recover the data in reverse order of the channel bitmask. Here we
    # match each reading to each channel using a dict
    axis_dict = {}
    for i in range(0, len(channels)):
        value = float((recovered_other_channels[i] % combine_factor) - combine_offset) / 100
        axis_dict[str(channels[i])] = _get_geoflex_axis_value_or_error(value)

    return axis_dict


def _get_geoflex_combined_data_size(chn_bitmask):
    allowed_channels_mask = 0x07
    chn_bitmask = chn_bitmask & allowed_channels_mask
    size_bits = 0
    sensor_per_frame = 0

    if chn_bitmask == 0x01 or chn_bitmask == 0x02 or chn_bitmask == 0x04:  # Only one axis enabled
        size_bits = 18
        sensor_per_frame = 7
    elif chn_bitmask == 0x03 or chn_bitmask == 0x05 or chn_bitmask == 0x06:  # Two axis enabled
        size_bits = 36
        sensor_per_frame = 6
    else:
        size_bits = 53
        sensor_per_frame = 5

    return size_bits, sensor_per_frame


def _get_dig_geoflex_data_str(msg):
    bitoffset = 0
    num_msg = _extract_bits_from_array(msg[:2], bitoffset, 4)
    bitoffset += 4
    geoflex_data_str = "; NumMsg: " + "%u" % num_msg
    num_sensors = _extract_bits_from_array(msg[:2], bitoffset, 3)
    bitoffset += 3
    geoflex_data_str += "; NumSensors: " + "%u" % num_sensors
    total_sensors = _extract_bits_from_array(msg[:2], bitoffset, 6)
    bitoffset += 6
    geoflex_data_str += "; TotalSensors: " + "%u" % total_sensors
    chn_present_or_error = _extract_bits_from_array(msg[:2], bitoffset, 3)

    if total_sensors > 0:
        geoflex_data_str += "; ChnBitMask: " + "%u" % chn_present_or_error
        combined_data_size, sensors_per_frame = _get_geoflex_combined_data_size(
            chn_present_or_error
        )

        bitoffset = 0
        geoflex_data_str += "; Readings:"

        for i in range(0, num_sensors):
            num_sensor = (sensors_per_frame * (num_msg - 1)) + (i + 1)
            geoflex_data_str += " Sensor %u" % (num_sensor)

            temperature = _extract_bits_from_array(msg[2:], bitoffset, 11)
            bitoffset += 11

            combined_data = _extract_bits_from_array(msg[2:], bitoffset, combined_data_size)
            bitoffset += combined_data_size

            if 0x400 != temperature:
                geoflex_data_str += ", Temp = %3.1f" % (float(_uint_to_int(temperature, 11)) / 10.0)
            else:
                geoflex_data_str += ", Temp = NaN"

            geoflex_data_str += ", Combined data = %u " % combined_data
            geoflex_data_str += (
                str(_get_geoflex_axis_readings(chn_present_or_error, combined_data)) + ";"
            )

    else:
        geoflex_data_str += "; GeneralErrorCode: " + "%u" % chn_present_or_error

    return geoflex_data_str


def _get_dig_measurand_data_str(msg):
    num_sensors_per_frame = [11, 13, 13, 13, 13, 13, 13, 11]
    saatop_threshold_error = 2000
    segments_threshold_error = 3000

    bitoffset = 0
    num_msg = _extract_bits_from_array(msg, bitoffset, 3)
    bitoffset += 3
    measurand_data_str = "; NumMsg: " + "%u" % num_msg
    total_sensors = _extract_bits_from_array(msg, bitoffset, 7)
    bitoffset += 7
    measurand_data_str += "; TotalSensors: " + "%u" % total_sensors
    num_sensors = _extract_bits_from_array(msg, bitoffset, 4)
    bitoffset += 4
    measurand_data_str += "; NumSensors: " + "%u" % num_sensors
    lp_protocol_flag = _extract_bits_from_array(msg, bitoffset, 1)
    bitoffset += 1
    measurand_data_str += "; Low Power protocol flag: " + "%u" % lp_protocol_flag
    if total_sensors == 0:
        general_error = _extract_bits_from_array(msg, bitoffset, 2)
        bitoffset += 2
        measurand_data_str += "; General Error: Error Code " + "%u" % general_error
        return measurand_data_str

    if total_sensors > 0:
        if num_msg == 0:
            measurand_data_str += "; SAATop Readings:"
            saatop_sn = _extract_bits_from_array(msg, bitoffset, 24)
            bitoffset += 24
            measurand_data_str += "; SAATop SN: " + "%u" % saatop_sn

            saatop_current = _extract_bits_from_array(msg, bitoffset, 16)
            if saatop_threshold_error <= saatop_current:
                measurand_data_str += (
                    "; Error in the current value; Error Code: " + "%u" % saatop_current
                )
            else:
                measurand_data_str += "; Current: " + "%u" % saatop_current
            bitoffset += 16

            saatop_voltage = _extract_bits_from_array(msg, bitoffset, 16)
            if saatop_threshold_error <= saatop_voltage:
                measurand_data_str += (
                    "; Error in the voltage value; Error Code: " + "%u" % saatop_voltage
                )
            else:
                measurand_data_str += "; Voltage: " + "%.1f" % (saatop_voltage / 10)
            bitoffset += 16

            segment0_sn = _extract_bits_from_array(msg, bitoffset, 24)
            bitoffset += 24
            measurand_data_str += "; First segment SN: " + "%u" % segment0_sn
        measurand_data_str += "; Segment Readings:\n"

        for i in range(0, num_sensors):

            num_sensor = sum(num_sensors_per_frame[0:num_msg]) + (i + 1)

            measurand_data_str += " Segment %u" % (num_sensor)

            temperature_raw = _extract_bits_from_array(msg, bitoffset, 12)
            bitoffset += 12

            acc_x_raw = _extract_bits_from_array(msg, bitoffset, 16)
            bitoffset += 16

            acc_y_raw = _extract_bits_from_array(msg, bitoffset, 16)
            bitoffset += 16

            acc_z_raw = _extract_bits_from_array(msg, bitoffset, 16)
            bitoffset += 16

            if segments_threshold_error >= temperature_raw:
                measurand_data_str += ", Temp raw = %u" % temperature_raw
                measurand_data_str += ", AccX raw = %u" % acc_x_raw
                measurand_data_str += ", AccY raw = %u" % acc_y_raw
                measurand_data_str += ", AccZ raw = %u; \n" % acc_z_raw
            else:
                measurand_data_str += (
                    ", Error in the segment data; Error Code %u \n" % temperature_raw
                )

    return measurand_data_str


def _get_dig_yieldpoint_data_str(msg):
    temp_decimals = 1
    temp_data_format = "%." + str(temp_decimals) + "f " + "\u00b0C"
    channels_data_size_dict = {0: 15, 1: 22, 2: 27, 3: 32}

    sensor_product_and_units_dict = {
        11: ["dUMP or GMM", ["mm"]],
        13: ["TEMP-1W", ["\u00b0C"]],
        21: ["d-GMM/dUMP", ["mm"]],
        23: ["d-micro", ["um"]],
        28: ["dPiezo or dPress", ["kPa"]],
        29: ["BluVibe(VW)", ["Hz"]],
        31: ["d2MPBX/EXTO", ["mm", "mm"]],
        41: ["d3", ["mm", "mm", "mm"]],
        51: ["d4", ["mm", "mm", "mm", "mm"]],
        61: ["d5", ["mm", "mm", "mm", "mm", "mm"]],
        71: ["d6", ["mm", "mm", "mm", "mm", "mm", "mm"]],
        75: ["d6", ["um", "um", "um", "um", "um", "um"]],
        89: ["dADICT(MDT)", ["bit", "bit", "bit", "bit", "bit", "bit", "uA"]],
        106: [
            "TEMP 10-1W",
            [
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
                "\u00b0C",
            ],
        ],
        139: ["dCSIRO", ["uE", "uE", "uE", "uE", "uE", "uE", "uE", "uE", "uE", "uE", "uE", "uE"]],
    }

    bitoffset = 0
    msg_ver = _extract_bits_from_array(msg, bitoffset, 2)
    bitoffset += 2
    yieldpoint_data_str = "; MsgVersion: " + "%u" % msg_ver

    num_channels = _extract_bits_from_array(msg, bitoffset, 4)
    bitoffset += 4

    if num_channels == 0:
        general_error = _extract_bits_from_array(msg, bitoffset, 4)
        yieldpoint_data_str += "; General Error: Error Code " + "%u" % general_error

    else:
        yieldpoint_data_str += "; Num Channels " + "%u" % num_channels

        channels_data_size = _extract_bits_from_array(msg, bitoffset, 2)
        bitoffset += 2
        yieldpoint_data_str += (
            "; Channels Data Size: %u bits" % channels_data_size_dict[channels_data_size]
        )

        data_loss = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        yieldpoint_data_str += "; Data Loss: %u" % data_loss

        num_decimals = _extract_bits_from_array(msg, bitoffset, 3)
        bitoffset += 3
        yieldpoint_data_str += "; Number of Decimals in data Channels: %u" % num_decimals
        channels_data_format = "%." + str(num_decimals) + "f"

        serial_number = _extract_bits_from_array(msg, bitoffset, 34)
        bitoffset += 34
        yieldpoint_data_str += "; Serial Number: %u" % serial_number

        sensor_type_str = str(serial_number)
        if len(sensor_type_str) == 9:
            sensor_type = int(sensor_type_str[4:6])
        elif len(sensor_type_str) == 10:
            sensor_type = int(sensor_type_str[4:7])
        else:
            sensor_type = 0

        if sensor_type in sensor_product_and_units_dict:
            yieldpoint_data_str += "; Sensor %s" % sensor_product_and_units_dict[sensor_type][0]
        else:
            sensor_type = 0
            yieldpoint_data_str += "; Unknown sensor type: unknown units"

        if num_channels > 1:
            temp = _extract_bits_from_array(msg, bitoffset, 12)
            bitoffset += 12
            yieldpoint_data_str += "; Temperature: " + temp_data_format % (
                _uint_to_int(temp, 12) / pow(10.0, temp_decimals)
            )
            num_channels -= 1

        channel = 0
        while channel < num_channels:
            channel_data = _extract_bits_from_array(
                msg, bitoffset, channels_data_size_dict[channels_data_size]
            )
            bitoffset += channels_data_size_dict[channels_data_size]
            yieldpoint_data_str += "; Channel %u: " % channel
            yieldpoint_data_str += channels_data_format % (
                _uint_to_int(channel_data, channels_data_size_dict[channels_data_size])
                / pow(10.0, num_decimals)
            )
            if sensor_type != 0:
                yieldpoint_data_str += (
                    " %s" % sensor_product_and_units_dict[sensor_type][1][channel]
                )
            channel += 1

    return yieldpoint_data_str


# timestamp 4, temp 2, channel1 3, channel2 3
def _get_tilt_data_str(msg):
    unpack_format = "!Ihii"

    unp_msg = _struct.unpack(unpack_format, msg)

    tilt_data_str = "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    tilt_data_str += "; Temperature: " + "%d" % (unp_msg[1])
    axis1 = unp_msg[2]
    axis2 = unp_msg[3]
    tilt_data_str += "; Axis1: {:02.5f}".format(axis1 / 1000000.0)
    tilt_data_str += "; Axis2: {:02.5f}".format(axis2 / 1000000.0)

    return tilt_data_str


#  Msg_Version(2b), Reserved(2b), ErrorCode(4b),
# HighPrecision(1b), Temperature(12b), Reserved2(3b), Counts1(4B),
# Counts2(4B), Counts3(4B), StDev1(20b), Stdev2(20b), StDev3(20b),
# Reserved3(4b)
def _get_tilt360_raw_data_str(msg):
    msg_decoder_dict = {
        "Version": {"position": 0, "bits": 2},
        "Reserved": {"position": 2, "bits": 2},
        "ErrorCode": {"position": 4, "bits": 4},
        "HighPrecision": {"position": 8, "bits": 1},
        "Reserved2": {"position": 9, "bits": 3},
        "Temperature": {
            "position": 12,
            "bits": 12,
            "function": lambda msg, value: float(_uint_to_int(value, msg["bits"])) / 10.0,
        },
        "Counts1": {
            "position": 24,
            "bits": 32,
            "function": lambda msg, value: _uint_to_float(value),
        },
        "Counts2": {
            "position": 56,
            "bits": 32,
            "function": lambda msg, value: _uint_to_float(value),
        },
        "Counts3": {
            "position": 88,
            "bits": 32,
            "function": lambda msg, value: _uint_to_float(value),
        },
        "StDev1": {"position": 120, "bits": 20},
        "StDev2": {"position": 140, "bits": 20},
        "StDev3": {"position": 160, "bits": 20},
        "Reserved3": {"position": 180, "bits": 4},
    }
    readings = {}
    for msg_type, proc_info in msg_decoder_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        # Ensure all the values are valid, if not replace the value with the error string.
        if "function" in proc_info:
            function = proc_info.get("function")
            readings[msg_type] = function(proc_info, value)
        else:
            readings[msg_type] = value

    # Get version
    tilt360_raw_data_str = "; Version: {}".format(readings["Version"])
    # Parse everything else
    tilt360_raw_data_str += "; ErrorCode: {}".format(readings["ErrorCode"])
    tilt360_raw_data_str += "; HighPrecision: {}".format(readings["HighPrecision"])
    tilt360_raw_data_str += "; Temperature: {}".format(readings["Temperature"])
    tilt360_raw_data_str += "; Counts1: {}".format(readings["Counts1"])
    tilt360_raw_data_str += "; Counts2: {}".format(readings["Counts2"])
    tilt360_raw_data_str += "; Counts3: {}".format(readings["Counts3"])
    tilt360_raw_data_str += "; StDev1: {}".format(readings["StDev1"])
    tilt360_raw_data_str += "; StDev2: {}".format(readings["StDev2"])
    tilt360_raw_data_str += "; StDev3: {}".format(readings["StDev3"])

    return tilt360_raw_data_str


# Timestamp 4, Msg_Version(2b), Reserved(2b), ErrorCode(4b),
# HighPrecision(1b), Temperature(12b), Axis1(21b), StDev1(20b),
# Axis2(21b), StDev2(20b), Axis3(21b), StDev3(20b).
def _get_tilt360_data_str(msg):
    header_dict = {
        "Timestamp": {"position": 0, "bits": 32},
        "Version": {"position": 32, "bits": 2},
        "Ch3Enabled": {"position": 34, "bits": 1},
        "Ch2Enabled": {"position": 35, "bits": 1},
        "Ch1Enabled": {"position": 36, "bits": 1},
        "ErrorCode": {"position": 37, "bits": 4},
        "HighPrecision": {"position": 41, "bits": 1},
        "Temperature": {
            "position": 42,
            "bits": 12,
            "function": lambda msg, value: float(_uint_to_int(value, msg["bits"])) / 10.0,
        },
    }
    readings = {}
    for msg_type, proc_info in header_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        # Ensure all the values are valid, if not replace the value with the error string.
        if "function" in proc_info:
            function = proc_info.get("function")
            readings[msg_type] = function(proc_info, value)
        else:
            readings[msg_type] = value

    timestamp = readings["Timestamp"]

    tilt360_data_str = "; Time: %u (%s)" % (timestamp, _second_to_time_iso8601(timestamp))
    tilt360_data_str += "; Version: {}".format(readings["Version"])
    ch3_en = readings["Ch3Enabled"]
    ch2_en = readings["Ch2Enabled"]
    ch1_en = readings["Ch1Enabled"]
    tilt360_data_str += "; TiltChEn: [{},{},{}]".format(ch3_en, ch2_en, ch1_en)

    tilt360_data_str += "; Error: {}".format(readings["ErrorCode"])
    tilt360_data_str += "; HighPrecision: {}".format(readings["HighPrecision"])
    tilt360_data_str += "; Temp: {}".format(readings["Temperature"])

    def tilt360_read_tilt_ch(msg, bitoffset, channel_number):
        axis = _extract_bits_from_array(msg, bitoffset, 21)
        bitoffset += 21
        stdev = _extract_bits_from_array(msg, bitoffset, 20)
        bitoffset += 20
        data_str = "; Axis{}: {}".format(channel_number, float(_uint_to_int(axis, 21)) / 10000.0)
        data_str += "; StDev{}: {}".format(channel_number, stdev)

        return [data_str, bitoffset]

    bitoffset = 54
    if 1 == ch1_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 1)
        tilt360_data_str += data_str_aux
    if 1 == ch2_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 2)
        tilt360_data_str += data_str_aux
    if 1 == ch3_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 3)
        tilt360_data_str += data_str_aux

    return tilt360_data_str


def _get_reception_opportunity_str(msg):
    header_dict = {
        "Version": {"position": 0, "bits": 4},
        "Reserved": {"position": 4, "bits": 3},
        "SamplingPeriod": {"position": 7, "bits": 17},
    }
    readings = {}
    for msg_type, proc_info in header_dict.iteritems():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        # Ensure all the values are valid, if not replace the value with the error string.
        if "function" in proc_info:
            function = proc_info.get("function")
            readings[msg_type] = function(proc_info, value)
        else:
            readings[msg_type] = value

    reception_opportunity_str = "; Version: {}".format(readings["Version"])
    reception_opportunity_str += "; Reserved: {}".format(readings["Reserved"])
    reception_opportunity_str += "; SamplingPeriod: {}".format(readings["SamplingPeriod"])

    return reception_opportunity_str


def _get_t360a_alert_str(msg):
    header_dict = {
        "Version": {"position": 0, "bits": 2},
        "Axis1State": {"position": 2, "bits": 2},
        "Axis2State": {"position": 4, "bits": 2},
        "Axis3State": {"position": 6, "bits": 2},
        "Reserved": {"position": 8, "bits": 6},
    }

    axis_state_to_string = {0: "Inactive", 1: "Active", 2: "Active Lower", 3: "Active Upper"}
    excess_code_to_value = [
        0.000000e-2,
        0.333333e-2,
        0.666666e-2,
        1.000000e-2,
        1.333333e-2,
        1.666666e-2,
        2.000000e-2,
        2.333333e-2,
        2.666666e-2,
        3.000000e-2,
        3.333333e-2,
        3.666666e-2,
        4.000000e-2,
        4.333333e-2,
        4.666666e-2,
        5.000000e-2,
        5.333333e-2,
        5.666666e-2,
        6.000000e-2,
        6.333333e-2,
        6.666666e-2,
        7.000000e-2,
        7.333333e-2,
        7.666666e-2,
        8.000000e-2,
        8.333333e-2,
        8.666666e-2,
        9.000000e-2,
        9.333333e-2,
        9.666666e-2,
        1.000000e-1,
        1.333333e-1,
        1.666666e-1,
        2.000000e-1,
        2.333333e-1,
        2.666666e-1,
        3.000000e-1,
        3.333333e-1,
        3.666666e-1,
        4.000000e-1,
        4.333333e-1,
        4.666666e-1,
        5.000000e-1,
        5.333333e-1,
        5.666666e-1,
        6.000000e-1,
        6.333333e-1,
        6.666666e-1,
        7.000000e-1,
        7.333333e-1,
        7.666666e-1,
        8.000000e-1,
        8.333333e-1,
        8.666666e-1,
        9.000000e-1,
        9.333333e-1,
        9.666666e-1,
        1.000000,
        1.333333,
        1.666666,
        2.000000,
        2.333333,
        2.666666,
        3.000000,
        3.333333,
        3.666666,
        4.000000,
        4.333333,
        4.666666,
        5.000000,
        5.333333,
        5.666666,
        6.000000,
        6.333333,
        6.666666,
        7.000000,
        7.333333,
        7.666666,
        8.000000,
        8.333333,
        8.666666,
        9.000000,
        9.333333,
        9.666666,
        1.000000e1,
        1.333333e1,
        1.666666e1,
        2.000000e1,
        2.333333e1,
        2.666666e1,
        3.000000e1,
        3.333333e1,
        3.666666e1,
        4.000000e1,
        4.333333e1,
        4.666666e1,
        5.000000e1,
        5.333333e1,
        5.666666e1,
        6.000000e1,
        6.333333e1,
        6.666666e1,
        7.000000e1,
        7.333333e1,
        7.666666e1,
        8.000000e1,
        8.333333e1,
        8.666666e1,
        9.000000e1,
        9.333333e1,
        9.666666e1,
        1.000000e2,
        1.333333e2,
        1.666666e2,
    ]

    msg_version = _extract_bits_from_array(
        msg, header_dict["Version"]["position"], header_dict["Version"]["bits"]
    )
    state_axes = []
    state_axes.append(
        _extract_bits_from_array(
            msg, header_dict["Axis1State"]["position"], header_dict["Axis1State"]["bits"]
        )
    )
    state_axes.append(
        _extract_bits_from_array(
            msg, header_dict["Axis2State"]["position"], header_dict["Axis2State"]["bits"]
        )
    )
    state_axes.append(
        _extract_bits_from_array(
            msg, header_dict["Axis3State"]["position"], header_dict["Axis3State"]["bits"]
        )
    )
    reserved = _extract_bits_from_array(
        msg, header_dict["Reserved"]["position"], header_dict["Reserved"]["bits"]
    )

    tilt360_alert_str = "; Version: {}".format(msg_version)
    tilt360_alert_str += "; Axis 1 State: {}".format(axis_state_to_string[state_axes[0]])
    tilt360_alert_str += "; Axis 2 State: {}".format(axis_state_to_string[state_axes[1]])
    tilt360_alert_str += "; Axis 3 State: {}".format(axis_state_to_string[state_axes[2]])
    tilt360_alert_str += "; Reserved: {}".format(reserved)

    bitoffset = 14
    for i in range(3):
        if (
            state_axes[i] == 2 or state_axes[i] == 3
        ):  # Active Uper and Active Lower states provide Excess information
            excess = _extract_bits_from_array(msg, bitoffset, 7)
            bitoffset += 7
            tilt360_alert_str += "; Axis {} Excess: {} ({:.2e})".format(
                i + 1, excess, excess_code_to_value[excess]
            )

    return tilt360_alert_str


# Timestamp 4, Msg_Version(2b), Reserved(2b), ErrorCode(4b),
# HighPrecision(1b), Temperature(12b), Axis1(21b), StDev1(20b),
# Axis2(21b), StDev2(20b), Axis3(21b), StDev3(20b).
def _get_tilt360alert_data_str(msg):
    header_dict = {
        "Timestamp": {"position": 0, "bits": 32},
        "Version": {"position": 32, "bits": 2},
        "Ch3Enabled": {"position": 34, "bits": 1},
        "Ch2Enabled": {"position": 35, "bits": 1},
        "Ch1Enabled": {"position": 36, "bits": 1},
        "ErrorCode": {"position": 37, "bits": 4},
        "HighPrecision": {"position": 41, "bits": 1},
        "Temperature": {
            "position": 42,
            "bits": 12,
            "function": lambda msg, value: float(_uint_to_int(value, msg["bits"])) / 10.0,
        },
    }
    axis_broken_threshold_to_string = {0: "Lower", 1: "Upper"}
    readings = {}
    for msg_type, proc_info in header_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        # Ensure all the values are valid, if not replace the value with the error string.
        if "function" in proc_info:
            function = proc_info.get("function")
            readings[msg_type] = function(proc_info, value)
        else:
            readings[msg_type] = value

    timestamp = readings["Timestamp"]

    tilt360_data_str = "; Time: %u (%s)" % (timestamp, _second_to_time_iso8601(timestamp))
    tilt360_data_str += "; Version: {}".format(readings["Version"])
    ch3_en = readings["Ch3Enabled"]
    ch2_en = readings["Ch2Enabled"]
    ch1_en = readings["Ch1Enabled"]
    tilt360_data_str += "; TiltChEn: [{},{},{}]".format(ch3_en, ch2_en, ch1_en)

    tilt360_data_str += "; Error: {}".format(readings["ErrorCode"])
    tilt360_data_str += "; HighPrecision: {}".format(readings["HighPrecision"])
    tilt360_data_str += "; Temp: {}".format(readings["Temperature"])

    def tilt360_read_tilt_ch(msg, bitoffset, channel_number):
        axis = _extract_bits_from_array(msg, bitoffset, 21)
        bitoffset += 21
        stdev = _extract_bits_from_array(msg, bitoffset, 20)
        bitoffset += 20
        data_str = "; Axis{}: {}".format(channel_number, float(_uint_to_int(axis, 21)) / 10000.0)
        data_str += "; StDev{}: {}".format(channel_number, stdev)

        return [data_str, bitoffset]

    bitoffset = 54
    if 1 == ch1_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 1)
        tilt360_data_str += data_str_aux
    if 1 == ch2_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 2)
        tilt360_data_str += data_str_aux
    if 1 == ch3_en:
        [data_str_aux, bitoffset] = tilt360_read_tilt_ch(msg, bitoffset, 3)
        tilt360_data_str += data_str_aux

    tilt360_data_str += "; Alerts Configured: {}".format(
        _extract_bits_from_array(msg, bitoffset, 1)
    )
    bitoffset += 1
    tilt360_data_str += "; Alert Triggered Message: {}".format(
        _extract_bits_from_array(msg, bitoffset, 1)
    )
    bitoffset += 1
    alerts_active = _extract_bits_from_array(msg, bitoffset, 1)
    tilt360_data_str += "; Alerts Active: {}".format(alerts_active)
    bitoffset += 1

    if 1 == alerts_active:
        ch3_abs_th_alert = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch2_abs_th_alert = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch1_abs_th_alert = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        tilt360_data_str += "; AbsTh Active Alerts: [{},{},{}]".format(
            ch3_abs_th_alert, ch2_abs_th_alert, ch1_abs_th_alert
        )

        ch3_ev_alert_active = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch2_ev_alert_active = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch1_ev_alert_active = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        tilt360_data_str += "; Event Active Alerts: [{},{},{}]".format(
            ch3_ev_alert_active, ch2_ev_alert_active, ch1_ev_alert_active
        )

        def tilt360_read_tilt_ch_alert(msg, bitoffset, channel_number):
            broken_axis = _extract_bits_from_array(msg, bitoffset, 1)
            bitoffset += 1
            cfg_threshold_broken = _extract_bits_from_array(msg, bitoffset, 15)
            bitoffset += 15
            data_str = "; Broken Threshold {}: {}".format(
                channel_number, axis_broken_threshold_to_string[broken_axis]
            )

            data_str += "; Threshold Config Value {}: {:d}".format(
                channel_number, _uint_to_int(cfg_threshold_broken, 15)
            )
            return [data_str, bitoffset]

        if 1 == ch1_abs_th_alert:
            [data_str_aux, bitoffset] = tilt360_read_tilt_ch_alert(msg, bitoffset, 1)
            tilt360_data_str += data_str_aux
        if 1 == ch2_abs_th_alert:
            [data_str_aux, bitoffset] = tilt360_read_tilt_ch_alert(msg, bitoffset, 2)
            tilt360_data_str += data_str_aux
        if 1 == ch3_abs_th_alert:
            [data_str_aux, bitoffset] = tilt360_read_tilt_ch_alert(msg, bitoffset, 3)
            tilt360_data_str += data_str_aux

    return tilt360_data_str


def _get_laser360_data_str(msg):
    header_dict = {
        "Timestamp": {"position": 0, "bits": 32},
        "Version": {"position": 32, "bits": 2},
        "Reserved": {"position": 34, "bits": 4},
        "LaserEnabled": {"position": 38, "bits": 1},
        "TiltEnabled": {"position": 39, "bits": 1},
    }
    bitoffset = 40

    timestamp = _extract_bits_from_array(
        msg, header_dict["Timestamp"]["position"], header_dict["Timestamp"]["bits"]
    )
    msg_version = _extract_bits_from_array(
        msg, header_dict["Version"]["position"], header_dict["Version"]["bits"]
    )
    reserved = _extract_bits_from_array(
        msg, header_dict["Reserved"]["position"], header_dict["Reserved"]["bits"]
    )
    laser_enabled = _extract_bits_from_array(
        msg, header_dict["LaserEnabled"]["position"], header_dict["LaserEnabled"]["bits"]
    )
    tilt_enabled = _extract_bits_from_array(
        msg, header_dict["TiltEnabled"]["position"], header_dict["TiltEnabled"]["bits"]
    )

    laser360_data_str = "; Time: %u (%s)" % (timestamp, _second_to_time_iso8601(timestamp))
    laser360_data_str += "; Version: {}".format(msg_version)
    laser360_data_str += "; Reserved: {}".format(reserved)
    laser360_data_str += "; LaserEn: {}".format(laser_enabled)
    laser360_data_str += "; TiltEn: {}".format(tilt_enabled)

    if 1 == tilt_enabled:
        ch3_en = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch2_en = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        ch1_en = _extract_bits_from_array(msg, bitoffset, 1)
        bitoffset += 1
        tilt_error_code = _extract_bits_from_array(msg, bitoffset, 4)
        bitoffset += 4
        tilt_temp = _extract_bits_from_array(msg, bitoffset, 12)
        bitoffset += 12
        laser360_data_str += "; TiltChEn: [{},{},{}]".format(ch3_en, ch2_en, ch1_en)
        laser360_data_str += "; TiltError: {}".format(tilt_error_code)
        laser360_data_str += "; TiltTemp: {}".format(float(_uint_to_int(tilt_temp, 12)) / 10.0)

        def laser360_read_tilt_ch(msg, bitoffset, channel_number):
            axis = _extract_bits_from_array(msg, bitoffset, 21)
            bitoffset += 21
            stdev = _extract_bits_from_array(msg, bitoffset, 20)
            bitoffset += 20
            data_str = "; Axis{}: {}".format(
                channel_number, float(_uint_to_int(axis, 21)) / 10000.0
            )
            data_str += "; StDev{}: {}".format(channel_number, stdev)

            return [data_str, bitoffset]

        if 1 == ch1_en:
            [data_str_aux, bitoffset] = laser360_read_tilt_ch(msg, bitoffset, 1)
            laser360_data_str += data_str_aux
        if 1 == ch2_en:
            [data_str_aux, bitoffset] = laser360_read_tilt_ch(msg, bitoffset, 2)
            laser360_data_str += data_str_aux
        if 1 == ch3_en:
            [data_str_aux, bitoffset] = laser360_read_tilt_ch(msg, bitoffset, 3)
            laser360_data_str += data_str_aux

    if 1 == laser_enabled:
        laser_decoder_dict = {
            "gain": {"position": 0, "bits": 1},
            "signalStrength": {"position": 1, "bits": 24},
            "temperature": {
                "position": 25,
                "bits": 11,
                "function": lambda msg, value: float(_uint_to_int(value, msg["bits"])) / 10.0,
            },
            "distance": {
                "position": 36,
                "bits": 24,
                "function": lambda msg, value: value / 10000.0,
            },  # Change units of the distance from 10/mm to m.
        }

        laser_readings = {}
        for msg_type, proc_info in laser_decoder_dict.items():
            value = _extract_bits_from_array(
                msg, proc_info["position"] + bitoffset, proc_info["bits"]
            )
            # Ensure all the values are valid, if not replace the value with the error string.
            if "function" in proc_info:
                function = proc_info.get("function")
                laser_readings[msg_type] = function(proc_info, value)
            else:
                laser_readings[msg_type] = value

        # First parse everthing then print it since we will change order

        laser360_data_str += "; Gain: {}".format(laser_readings["gain"])
        laser360_data_str += "; SignalStrength: {}".format(laser_readings["signalStrength"])
        laser360_data_str += "; Temperature: {}".format(laser_readings["temperature"])
        laser360_data_str += "; Distance: {}".format(
            laser_readings["distance"]
        )  # From 10/mm to meters

    return laser360_data_str


def _get_laser360_ch_config_str(msg):
    laser360_ch_config_dict = {
        "Version": {"position": 0, "bits": 2},
        "Reserved": {"position": 2, "bits": 1},
        "LaserEnabled": {"position": 3, "bits": 1},
        "TiltEnabled": {"position": 4, "bits": 1},
        "TiltCh3": {"position": 5, "bits": 1},
        "TiltCh2": {"position": 6, "bits": 1},
        "TiltCh1": {"position": 7, "bits": 1},
    }

    config_params = {}
    for msg_type, proc_info in laser360_ch_config_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        config_params[msg_type] = value

    laser360_ch_config_str = "; Version: {}".format(config_params["Version"])
    laser360_ch_config_str += "; Reserved: {}".format(config_params["Reserved"])
    laser360_ch_config_str += "; LaserEnabled: {}".format(config_params["LaserEnabled"])
    laser360_ch_config_str += "; TiltEnabled: {}".format(config_params["TiltEnabled"])
    laser360_ch_config_str += "; TiltChEn: [{},{},{}]".format(
        config_params["TiltCh3"], config_params["TiltCh2"], config_params["TiltCh1"]
    )

    return laser360_ch_config_str


def _get_tilt360_ch_config_str(msg):
    tilt360_ch_config_dict = {
        "Version": {"position": 0, "bits": 2},
        "Reserved": {"position": 2, "bits": 3},
        "Ch3": {"position": 5, "bits": 1},
        "Ch2": {"position": 6, "bits": 1},
        "Ch1": {"position": 7, "bits": 1},
    }

    config_params = {}
    for msg_type, proc_info in tilt360_ch_config_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        config_params[msg_type] = value

    tilt360_ch_config_str = "; Version: {}".format(config_params["Version"])
    tilt360_ch_config_str += "; Reserved: {}".format(config_params["Reserved"])
    tilt360_ch_config_str += "; ChEn: [{},{},{}]".format(
        config_params["Ch3"], config_params["Ch2"], config_params["Ch1"]
    )

    return tilt360_ch_config_str


def _get_tilt360alert_ch_config_str(msg):
    tilt360alert_ch_config_dict = {
        "Version": {"position": 0, "bits": 3},
        "Reserved": {"position": 3, "bits": 1},
        "Ch3Enabled": {"position": 4, "bits": 1},
        "Ch2Enabled": {"position": 5, "bits": 1},
        "Ch1Enabled": {"position": 6, "bits": 1},
        "Ch3EnabledAlert": {"position": 7, "bits": 1},
        "Ch2EnabledAlert": {"position": 8, "bits": 1},
        "Ch1EnabledAlert": {"position": 9, "bits": 1},
        "ThAlertOffDelay": {"position": 10, "bits": 4},
        "MaxThAxis1": {"position": 14, "bits": 15},
        "MinThAxis1": {"position": 29, "bits": 15},
        "MaxThAxis2": {"position": 44, "bits": 15},
        "MinThAxis2": {"position": 59, "bits": 15},
        "MaxThAxis3": {"position": 74, "bits": 15},
        "MinThAxis3": {"position": 89, "bits": 15},
    }

    config_params = {}
    for msg_type, proc_info in tilt360alert_ch_config_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        config_params[msg_type] = value

    tilt360_ch_config_str = "; Version: {}".format(config_params["Version"])
    tilt360_ch_config_str += "; Reserved: {}".format(config_params["Reserved"])
    tilt360_ch_config_str += "; ChEn: [{},{},{}]".format(
        config_params["Ch3Enabled"], config_params["Ch2Enabled"], config_params["Ch1Enabled"]
    )
    tilt360_ch_config_str += "; ChAlertEn: [{},{},{}]".format(
        config_params["Ch3EnabledAlert"],
        config_params["Ch2EnabledAlert"],
        config_params["Ch1EnabledAlert"],
    )
    tilt360_ch_config_str += "; Absolute Threshold Alert Off Delay: {}".format(
        config_params["ThAlertOffDelay"]
    )
    tilt360_ch_config_str += "; Absolute Threshold Axis 1: [Upper: {:d}, Lower: {:d}]".format(
        _uint_to_int(config_params["MaxThAxis1"], 15), _uint_to_int(config_params["MinThAxis1"], 15)
    )
    tilt360_ch_config_str += "; Absolute Threshold Axis 2: [Upper: {:d}, Lower: {:d}]".format(
        _uint_to_int(config_params["MaxThAxis2"], 15), _uint_to_int(config_params["MinThAxis2"], 15)
    )
    tilt360_ch_config_str += "; Absolute Threshold Axis 3: [Upper: {:d}, Lower: {:d}]".format(
        _uint_to_int(config_params["MaxThAxis3"], 15), _uint_to_int(config_params["MinThAxis3"], 15)
    )

    return tilt360_ch_config_str


def _get_tilt360alert_ch_config_sp_alert_aggcfg_str(msg):
    tilt360alert_ch_config_sp_alert_dict = {
        "AggCfgMsgVersion": {"position": 0, "bits": 4},
        "AggCfgReserved": {"position": 4, "bits": 4},
        "ChCfgMsgVersion": {"position": 8, "bits": 3},
        "ChCfgReserved": {"position": 11, "bits": 1},
        "Ch3Enabled": {"position": 12, "bits": 1},
        "Ch2Enabled": {"position": 13, "bits": 1},
        "Ch1Enabled": {"position": 14, "bits": 1},
        "Ch3EnabledAlert": {"position": 15, "bits": 1},
        "Ch2EnabledAlert": {"position": 16, "bits": 1},
        "Ch1EnabledAlert": {"position": 17, "bits": 1},
        "ThAlertOffDelay": {"position": 18, "bits": 4},
        "MaxThAxis1": {"position": 22, "bits": 15},
        "MinThAxis1": {"position": 37, "bits": 15},
        "MaxThAxis2": {"position": 52, "bits": 15},
        "MinThAxis2": {"position": 67, "bits": 15},
        "MaxThAxis3": {"position": 82, "bits": 15},
        "MinThAxis3": {"position": 97, "bits": 15},
        "AlertSP": {"position": 112, "bits": 24},
    }

    config_params = {}
    for msg_type, proc_info in tilt360alert_ch_config_sp_alert_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        config_params[msg_type] = value

    tilt360_ch_config_sp_alert_str = "; AggCfg Version: {}".format(
        config_params["AggCfgMsgVersion"]
    )
    tilt360_ch_config_sp_alert_str += "; AggCfg Reserved: {}".format(
        config_params["AggCfgReserved"]
    )
    tilt360_ch_config_sp_alert_str += "; Ch Cfg Version: {}".format(
        config_params["ChCfgMsgVersion"]
    )
    tilt360_ch_config_sp_alert_str += "; Ch Cfg Reserved: {}".format(config_params["ChCfgReserved"])
    tilt360_ch_config_sp_alert_str += "; ChEn: [{},{},{}]".format(
        config_params["Ch3Enabled"], config_params["Ch2Enabled"], config_params["Ch1Enabled"]
    )
    tilt360_ch_config_sp_alert_str += "; ChAlertEn: [{},{},{}]".format(
        config_params["Ch3EnabledAlert"],
        config_params["Ch2EnabledAlert"],
        config_params["Ch1EnabledAlert"],
    )
    tilt360_ch_config_sp_alert_str += "; Absolute Threshold Alert Off Delay: {}".format(
        config_params["ThAlertOffDelay"]
    )
    tilt360_ch_config_sp_alert_str += (
        "; Absolute Threshold Axis 1: [Upper: {:d}, Lower: {:d}]".format(
            _uint_to_int(config_params["MaxThAxis1"], 15),
            _uint_to_int(config_params["MinThAxis1"], 15),
        )
    )
    tilt360_ch_config_sp_alert_str += (
        "; Absolute Threshold Axis 2: [Upper: {:d}, Lower: {:d}]".format(
            _uint_to_int(config_params["MaxThAxis2"], 15),
            _uint_to_int(config_params["MinThAxis2"], 15),
        )
    )
    tilt360_ch_config_sp_alert_str += (
        "; Absolute Threshold Axis 3: [Upper: {:d}, Lower: {:d}]".format(
            _uint_to_int(config_params["MaxThAxis3"], 15),
            _uint_to_int(config_params["MinThAxis3"], 15),
        )
    )
    tilt360_ch_config_sp_alert_str += "; Alert SP: {}".format(config_params["AlertSP"])

    return tilt360_ch_config_sp_alert_str


def _get_dig_6geo_legacy_data_str(msg):
    msg_hdr = _struct.unpack("!B", msg[:1])

    gsi_data_str = "; EOD: " + "%u" % ((msg_hdr[0] & 0x80) >> 7)
    num_channels = (msg_hdr[0] & 0x70) >> 4
    gsi_data_str += "; NumCh: " + "%u" % (num_channels)
    gsi_data_str += "; NumMsg: " + "%u" % (msg_hdr[0] & 0x0F)

    bitoffset = 0

    for i in range(0, num_channels):
        num_axis = (_extract_bits_from_array(msg[1:], bitoffset, 1)) + 1
        gsi_data_str += "; Ch %u: Axis = %u" % (i, num_axis)
        bitoffset = bitoffset + 1

        temp = _extract_bits_from_array(msg[1:], bitoffset, 11)
        if 0x400 != temp:
            gsi_data_str += ", Temp = %3.1f" % (float(_uint_to_int(temp, 11)) / 10.0)
        else:
            gsi_data_str += ", Temp = NaN"
        bitoffset = bitoffset + 11

        axe = _extract_bits_from_array(msg[1:], bitoffset, 20)
        if 0x80000 != axe:
            gsi_data_str += ", Axe1 = %2.4f" % (float(_uint_to_int(axe, 20)) / 10000.0)
        else:
            gsi_data_str += ", Axe1 = NaN"
        bitoffset = bitoffset + 20

        if 2 == num_axis:
            axe = _extract_bits_from_array(msg[1:], bitoffset, 20)
            if 0x80000 != axe:
                gsi_data_str += ", Axe2 = %2.4f" % (float(_uint_to_int(axe, 20)) / 10000.0)
            else:
                gsi_data_str += ", Axe2 = NaN"
            bitoffset = bitoffset + 20

    return gsi_data_str


def _get_dig_6geo_v3_data_aux_to_value(encoded_aux):
    if 0 == encoded_aux:
        real_aux = 1
    else:
        real_aux = encoded_aux * 1000

    return real_aux


def _get_dig_6geo_v3_data_err_to_string(encoded_error):
    error_switcher = {
        0: "Validation Models",
        1: "Validation Units",
        2: "Validation Aux Unit",
        3: "Validation max sensor channels",
        4: "No readings",
        5: "Power supply low",
    }

    return error_switcher.get(encoded_error, "Unrecognized error")


def _get_dig_6geo_v3_data_model_to_string(encoded_model):
    model_switcher = {
        0: "Generic",
        1: "IPI",
        2: "Tiltmeter",
        3: "Settlement Gauge",
        4: "Pressure Cell",
        5: "Load Cell",
        6: "Piezometer",
        7: "RDS",
        8: "Pendulum",
        9: "Extensometer",
        10: "Crackmeter",
        11: "Strain Gauge",
        12: "Thermometer",
        13: "Extensoinclinometer",
    }

    return model_switcher.get(encoded_model, "Unrecognized model")


def _get_dig_6geo_v3_data_unit_decimals_to_list(encoded_unit):
    unit_switcher = {
        1: ["mV", 2],
        2: ["bar", 5],
        3: ["mbar", 3],
        4: ["atm", 5],
        5: ["psi", 4],
        6: ["Pa", 0],
        7: ["kPa", 3],
        8: ["MPa", 6],
        9: ["mmH2O", 1],
        10: ["mH2O", 4],
        11: ["inH2O", 3],
        12: ["ftH2O", 4],
        13: ["mmHg", 3],
        14: ["cmHg", 4],
        15: ["inHg", 4],
        16: ["Kg/cm2", 5],
        17: ["Kg/m2", 1],
        18: ["lb/in2", 4],
        19: ["lb/ft2", 2],
        20: ["N/cm2", 4],
        21: ["N/m2", 0],
        22: ["t/m2", 4],
        23: ["t(UK)/ft2", 5],
        24: ["t(USA)/ft2", 5],
        25: ["Degrees C", 1],
        26: ["20kSin(angle)", 2],
        27: ["Sin(angle)", 6],
        28: ["Angle in Degrees", 4],
        29: ["Percent RH", 1],
        30: ["mV/V", 4],
        31: ["mm", 3],
        32: ["mm/m", 3],
        33: ["inches/feet", 5],
        34: ["kSin(angle)", 0],
        35: ["Volt", 1],
        36: ["kN", 2],
        37: ["Micro Strain", 2],
        38: ["inch", 5],
        39: ["feet", 6],
    }

    return unit_switcher.get(encoded_unit, "Unrecognized unit")


def _get_dig_6geo_v3_data_str(msg):
    header_dict = {
        "hdr_version": {"position": 0, "bits": 2},
        "eod": {"position": 2, "bits": 1},
        "sensors_number": {"position": 3, "bits": 3},
        "frame_number": {"position": 6, "bits": 3},
        "total_sensors": {"position": 9, "bits": 5},
        "model": {"position": 14, "bits": 5},
        "units": {"position": 19, "bits": 6},
        "aux": {"position": 25, "bits": 7},
    }
    msg_hdr = msg[:4]

    gsi_data_str = "; HV: " + "%u" % (
        _extract_bits_from_array(
            msg_hdr, header_dict["hdr_version"]["position"], header_dict["hdr_version"]["bits"]
        )
    )
    eod = _extract_bits_from_array(
        msg_hdr, header_dict["eod"]["position"], header_dict["eod"]["bits"]
    )
    gsi_data_str += "; EOD: " + "%u" % (eod)
    num_sensors = _extract_bits_from_array(
        msg_hdr, header_dict["sensors_number"]["position"], header_dict["sensors_number"]["bits"]
    )

    if 0 != num_sensors:
        gsi_data_str += "; NumSensors: " + "%u" % (num_sensors)
        frame_number = _extract_bits_from_array(
            msg_hdr, header_dict["frame_number"]["position"], header_dict["frame_number"]["bits"]
        )
        gsi_data_str += "; NumMsg: " + "%u" % (frame_number)
        total_num_sensors = _extract_bits_from_array(
            msg_hdr, header_dict["total_sensors"]["position"], header_dict["total_sensors"]["bits"]
        )
        gsi_data_str += "; TotalNumSensors: " + "%u" % (total_num_sensors)
        encoded_model = _extract_bits_from_array(
            msg_hdr, header_dict["model"]["position"], header_dict["model"]["bits"]
        )
        gsi_data_str += "; Model: " + _get_dig_6geo_v3_data_model_to_string(encoded_model)
        encoded_unit = _extract_bits_from_array(
            msg_hdr, header_dict["units"]["position"], header_dict["units"]["bits"]
        )
        unit_and_decimals = _get_dig_6geo_v3_data_unit_decimals_to_list(encoded_unit)
        gsi_data_str += "; Physical Unit: " + unit_and_decimals[0]
        if 34 == encoded_unit:  # kSin(angle)
            encoded_aux = _extract_bits_from_array(
                msg_hdr, header_dict["aux"]["position"], header_dict["aux"]["bits"]
            )
            aux_value = _get_dig_6geo_v3_data_aux_to_value(encoded_aux)
            unit_and_decimals[1] = int(
                max(0, 6 - _math.floor(_math.log10(aux_value)))
            )  # Special case of decimals number
            gsi_data_str += "; Aux Value: " + str(aux_value)

        if 1 == eod:
            if frame_number > 1:
                sensors_per_frame = (total_num_sensors - num_sensors) / (frame_number - 1)
            else:
                sensors_per_frame = total_num_sensors
        else:
            sensors_per_frame = num_sensors
    else:
        encoded_error = _extract_bits_from_array(
            msg_hdr, header_dict["aux"]["position"], header_dict["aux"]["bits"]
        )
        gsi_data_str += "; Chain error: " + _get_dig_6geo_v3_data_err_to_string(encoded_error)

    bitoffset = 0

    for i in range(0, num_sensors):
        num_sensor = (sensors_per_frame * (frame_number - 1)) + (i + 1)
        num_chn = _extract_bits_from_array(msg[4:], bitoffset, 3)
        gsi_data_str += "; Sensor %u: Channels = %u" % (num_sensor, num_chn)
        bitoffset = bitoffset + 3

        if 0 < num_chn:
            temp = _extract_bits_from_array(msg[4:], bitoffset, 11)
            if 0x400 != temp:
                gsi_data_str += ", Temp = %3.1f" % (float(_uint_to_int(temp, 11)) / 10.0)
            else:
                gsi_data_str += ", Temp = NaN"
            bitoffset = bitoffset + 11

            for i in range(0, num_chn):
                gsi_data_str += ", Chn " + str(i + 1)
                reading = _extract_bits_from_array(msg[4:], bitoffset, 21)
                if 0x100000 != reading:
                    # Extensoinclinometer channel 3 always treated as mm
                    if 13 == encoded_model and i == 2:
                        decimals = 3
                    else:
                        decimals = unit_and_decimals[1]

                    if 0 != decimals:
                        factor = float(_math.pow(10, -decimals))
                        real_reading = _uint_to_int(reading, 21) * factor
                    else:
                        real_reading = _uint_to_int(reading, 21)
                    output_format = "." + str(decimals) + "f"
                    gsi_data_str += " Reading = " + format(real_reading, output_format)
                else:
                    gsi_data_str += " Reading = NaN"
                bitoffset = bitoffset + 21
        else:
            gsi_data_str += ", Error on sensor"

    return gsi_data_str


def _get_dig_mdt_data_str(msg):
    msg_hdr = _struct.unpack("!B", msg[:1])

    gsi_data_str = "; EOD: " + "%u" % ((msg_hdr[0] & 0x80) >> 7)
    num_channels = (msg_hdr[0] & 0x70) >> 4
    gsi_data_str += "; NumCh: " + "%u" % (num_channels)
    gsi_data_str += "; NumMsg: " + "%u" % ((msg_hdr[0] & 0x0E) >> 1)
    gsi_data_str += "; Cal: " + "%u" % (msg_hdr[0] & 0x01)

    bitoffset = 0
    gsi_data_str += "; SN: "
    for i in range(0, 15):
        temp = _extract_bits_from_array(msg[1:], bitoffset, 8)
        gsi_data_str += "%c" % temp
        bitoffset = bitoffset + 8

    for i in range(0, num_channels):
        delta = _extract_bits_from_array(msg[1:], bitoffset, 21)
        delta_f = _uint_to_int(delta, 21) / 1000.0
        # gsi_data_str += "; Delta %d: %d"%(i,delta)
        gsi_data_str += "; Delta %d: %.3f" % (i, delta_f)
        bitoffset = bitoffset + 21

    return gsi_data_str


# 1 -> protocol & num channels; 2-177 -> ids of the channels.
# Sizes: 6, 9, 13, 16, 20, 23, 27, 30, 34, 37, 41, 44, 48, 51, 55, 58, 62, 65, 69, 72, 76, 79, 83, 86, 90, 93, 97,
# 100, 104, 107, 111, 114, 118, 121, 125, 128, 132, 135, 139, 142, 146, 149, 153, 156, 160, 163, 167, 170, 174, 177
def _get_gsi_ch_config_str(msg):
    first_byte = _struct.unpack("B", msg[:1])
    gsi_ch_config_str = "; Protocol: %u" % ((first_byte[0] & 0x40) >> 6)
    gsi_ch_config_str += "; RSTDelayEnabled: %u" % ((first_byte[0] & 0x80) >> 7)
    num_channels = first_byte[0] & 0x3F
    gsi_ch_config_str += "; NumChannels: %u" % num_channels

    i = 0
    while i < num_channels:
        if num_channels - i >= 2:  # Two channels or more present
            unp_2_channels = _struct.unpack(
                "!IBBB", msg[((i // 2) * 7 + 1) : ((i // 2) * 7 + 1 + 7)]
            )
            gsi_ch_config_str += "; Ch%u: %u" % (i, (unp_2_channels[0] >> 4))
            i = i + 1
            gsi_ch_config_str += "; Ch%u: %u" % (
                i,
                (
                    ((unp_2_channels[0] & 0x0F) << 24)
                    | (unp_2_channels[1] << 16)
                    | (unp_2_channels[2] << 8)
                    | (unp_2_channels[3])
                ),
            )
            i = i + 1
        else:  # Only one (and last) channel present
            unp_1_channel = _struct.unpack("!I", msg[i // 2 * 7 + 1 : (i // 2) * 7 + 1 + 4])
            gsi_ch_config_str += "; Ch%u: %u" % (i, (unp_1_channel[0] >> 4))
            i = i + 1

    return gsi_ch_config_str


def _get_6geo_ch_config_str(msg):
    common_cfg = _struct.unpack("BBB", msg[:3])

    num_channels = common_cfg[0] & 0x3F
    sisgeo_ch_config_str = "; NumChannels: %u" % num_channels
    sisgeo_ch_config_str += "; AddrDelay: %u" % common_cfg[1]
    sisgeo_ch_config_str += "; WarmingDelay: %u" % common_cfg[2]

    i = 0
    while i < num_channels:
        unp_channel = _struct.unpack("B", msg[i + 3 : i + 4])
        sisgeo_ch_config_str += "; Ch%u: %u" % (i, (unp_channel[0]))
        i = i + 1

    return sisgeo_ch_config_str


def _get_mdt_ch_config_str(msg):
    common_cfg = _struct.unpack("B", msg[:3])

    mdt_ch_config_str = "; Enabled: %u" % common_cfg[0]

    return mdt_ch_config_str


def _get_geoflex_ch_config_str(msg):
    num_sensors_mask = 0x3F
    sensor_model_bits = 3
    num_channels_bits = 3 + 2  # reserved
    data_wait_bits = 16
    sensor_id_bits = 12
    bitoffset = 0
    sensor_model_dict = {
        0: "DGSI - Geoflex",
        1: "Soil instruments - GEOSmart",
        2: "Roctest - Geostring",
        3: "Soil instruments - Smart IPI",
    }

    first_byte = _struct.unpack("B", msg[:1])
    num_sensors = first_byte[0] & num_sensors_mask
    geoflex_ch_str = "; NumSensors: %u" % num_sensors

    sensor_model = _extract_bits_from_array(msg[1:], 0, sensor_model_bits)
    geoflex_ch_str += "; Sensor Model: %x (%s)" % (sensor_model, sensor_model_dict[sensor_model])
    bitoffset = sensor_model_bits

    channels_bitmask = _extract_bits_from_array(msg[1:], bitoffset, num_channels_bits)
    geoflex_ch_str += "; Channels bitmask: %x" % channels_bitmask
    bitoffset += num_channels_bits

    data_wait = _extract_bits_from_array(msg[1:], bitoffset, data_wait_bits)
    geoflex_ch_str += "; Data wait time (ms): %u" % data_wait

    if num_sensors > 0:
        bitoffset = 0
        for i in range(num_sensors):
            sensor_id = _extract_bits_from_array(msg[4:], bitoffset, sensor_id_bits)
            bitoffset += sensor_id_bits
            geoflex_ch_str += "; Sensor %u ID: %u" % (i + 1, sensor_id)

    return geoflex_ch_str


def _get_gmm_instructions_cfg(msg):
    swap_endianess_size_bits = 8
    num_global_inst_size_bits = 8
    global_inst_size_bits = 15 * 8
    num_sensor_inst_size_bits = 8
    config_id_size_bits = 16  # 12 de config id + 4 reserved a 0
    timeout_size_bits = 24

    offset_bits = 8  # skip the ConfigVersion field
    config_id = _extract_bits_from_array(msg, offset_bits, config_id_size_bits)
    gm_ch_str = "; config_id: %u" % config_id
    offset_bits += config_id_size_bits

    endianess = _extract_bits_from_array(msg, offset_bits, swap_endianess_size_bits)
    offset_bits += swap_endianess_size_bits
    gm_ch_str += "; Swap Modbus Word Sensor Endianess: %u" % endianess

    timeout = _extract_bits_from_array(msg, offset_bits, timeout_size_bits)
    offset_bits += timeout_size_bits
    gm_ch_str += "; timeout: %u" % timeout

    num_global_inst = _extract_bits_from_array(msg, offset_bits, num_global_inst_size_bits)
    offset_bits += num_global_inst_size_bits
    gm_ch_str += "; num_global_inst: %u" % num_global_inst
    # We don't parse instructions here

    offset_bits += global_inst_size_bits
    num_sensor_inst = _extract_bits_from_array(msg, offset_bits, num_sensor_inst_size_bits)
    offset_bits += num_sensor_inst_size_bits
    gm_ch_str += "; num_sensor_inst: %u" % num_sensor_inst
    # We don't parse instructions here

    return gm_ch_str


def _get_gmm_channel_cfg(msg):
    modbus_baudrate_bits = 24
    data_bits_n_bits = 8
    parity_n_bits = 8
    stop_bits_n_bits = 8
    number_sensors_bits = 8
    id_sensor_size_bits = 8
    parity_dic = {0: "0 (None)", 1: "1 (even)", 2: "2 (odd)"}
    stop_bits_dic = {0: "0 (0.5 bit)", 1: "1 (1 bit)", 2: "2 (1.5 bit)", 3: "3 (2 bit)"}

    offset_bits = 0
    baudrate = _extract_bits_from_array(msg, offset_bits, modbus_baudrate_bits)
    gm_ch_str = "; baudrate: %u" % baudrate
    offset_bits += modbus_baudrate_bits
    data_bits = _extract_bits_from_array(msg, offset_bits, data_bits_n_bits)
    gm_ch_str += "; data bits: %u" % data_bits
    offset_bits += data_bits_n_bits
    parity = _extract_bits_from_array(msg, offset_bits, parity_n_bits)
    gm_ch_str += "; parity: %s" % parity_dic[parity]
    offset_bits += parity_n_bits
    stop_bits = _extract_bits_from_array(msg, offset_bits, stop_bits_n_bits)
    gm_ch_str += "; stop bits: %s" % stop_bits_dic[stop_bits]
    offset_bits += stop_bits_n_bits
    number_sensors = _extract_bits_from_array(msg, offset_bits, number_sensors_bits)
    gm_ch_str += "; number of sensors: %u" % number_sensors
    offset_bits += number_sensors_bits
    for x in range(0, number_sensors):
        id_sensor = _extract_bits_from_array(
            msg, offset_bits + (x * id_sensor_size_bits), id_sensor_size_bits
        )
        gm_ch_str += " id: %u" % id_sensor
    return gm_ch_str


def _get_measurand_ch_config_str(msg):
    protocol_bits = 8
    num_sensors_bits = 8
    protocol_dic = {0: "0 (Regular Protocol)", 1: "1 (Low Power Protocol)"}

    offset_bits = 0
    protocol = _extract_bits_from_array(msg, offset_bits, protocol_bits)
    meas_ch_str = "; protocol: %s" % protocol_dic[protocol]
    offset_bits += protocol_bits
    num_sensors = _extract_bits_from_array(msg, offset_bits, num_sensors_bits)
    meas_ch_str += "; number of sensors: %u" % num_sensors
    return meas_ch_str


def _get_dig_ch_config_str(msg):
    msg_hdr = _struct.unpack("!BB", msg[:2])

    if msg_hdr[0] == 0:
        dig_ch_config_str = "; GSI; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_gsi_ch_config_str(msg[2:])
    elif msg_hdr[0] == 1:
        dig_ch_config_str = "; 6GEO_legacy; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_6geo_ch_config_str(msg[2:])
    elif msg_hdr[0] == 2:
        dig_ch_config_str = "; MDT; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_mdt_ch_config_str(msg[2:])
    elif msg_hdr[0] == 3:
        dig_ch_config_str = "; 6GEO_V3; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_6geo_ch_config_str(msg[2:])
    elif msg_hdr[0] == 4:
        dig_ch_config_str = "; Geoflex; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_geoflex_ch_config_str(msg[2:])
    elif msg_hdr[0] == 5:
        dig_ch_config_str = "; Generic modbus; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_gmm_channel_cfg(msg[2:])
    elif msg_hdr[0] == 6:
        dig_ch_config_str = "; Measurand SAAV; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_measurand_ch_config_str(msg[2:])
    elif msg_hdr[0] == 7:
        dig_ch_config_str = "; YieldPoint; Version: %u" % (msg_hdr[1])
    elif msg_hdr[0] == 8:
        dig_ch_config_str = "; Extended Measurand SAAV; Version: %u" % (msg_hdr[1])
        dig_ch_config_str += _get_measurand_ch_config_str(msg[2:])
    else:
        dig_ch_config_str = "; Unknown sensor type (%u)" % (msg_hdr[0])

    return dig_ch_config_str


def _get_tilt_ch_calib_str(msg):
    msg_hdr = _struct.unpack("!Iffffffffff", msg)

    tilt_ch_calib_str = "; Time: %s" % (_second_to_time_iso8601(msg_hdr[0]))
    tilt_ch_calib_str += "; Offset [1]: %f" % (msg_hdr[1])
    tilt_ch_calib_str += "; CoefA [1]: %f" % (msg_hdr[2])
    tilt_ch_calib_str += "; CoefB [1]: %f" % (msg_hdr[3])
    tilt_ch_calib_str += "; CoefC [1]: %f" % (msg_hdr[4])
    tilt_ch_calib_str += "; CoefD [1]: %f" % (msg_hdr[5])
    tilt_ch_calib_str += "; Offset [2]: %f" % (msg_hdr[6])
    tilt_ch_calib_str += "; CoefA [2]: %f" % (msg_hdr[7])
    tilt_ch_calib_str += "; CoefB [2]: %f" % (msg_hdr[8])
    tilt_ch_calib_str += "; CoefC [2]: %f" % (msg_hdr[9])
    tilt_ch_calib_str += "; CoefD [2]: %f" % (msg_hdr[10])

    return tilt_ch_calib_str


def _get_tilt360_ch_calib_str(msg):
    msg_hdr = _struct.unpack("!Iffffff", msg)

    tilt360_ch_calib_str = "; Time: %u (%s)" % (msg_hdr[0], _second_to_time_iso8601(msg_hdr[0]))
    tilt360_ch_calib_str += "; Offset [1]: %f" % (msg_hdr[1])
    tilt360_ch_calib_str += "; Gain [1]: %f" % (msg_hdr[2])
    tilt360_ch_calib_str += "; Offset [2]: %f" % (msg_hdr[3])
    tilt360_ch_calib_str += "; Gain [2]: %f" % (msg_hdr[4])
    tilt360_ch_calib_str += "; Offset [3]: %f" % (msg_hdr[5])
    tilt360_ch_calib_str += "; Gain [3]: %f" % (msg_hdr[6])

    return tilt360_ch_calib_str


def _get_sp_config_str(msg):
    unp_msg = _struct.unpack("!BH", msg)
    sampling_period = (unp_msg[0] << 16) | unp_msg[1]
    gsi_sp_config_str = "; SamplingPeriod: " + str(sampling_period)
    return gsi_sp_config_str


def _get_t360a_sp_alert_config_str(msg):
    unp_msg = _struct.unpack("!BH", msg)
    sampling_period = (unp_msg[0] << 16) | unp_msg[1]
    sp_config_str = "; SamplingPeriod of Alert State: " + str(sampling_period)
    return sp_config_str


def _get_supply_threshold_str(msg):
    unp_msg = _struct.unpack("!H", msg)
    threshold = unp_msg[0]
    dig_threshold_str = "; Threshold value: " + str(threshold * 0.1) + " Vdc"
    return dig_threshold_str


def _get_vw_magnitude_threshold_str(msg):
    unp_msg = _struct.unpack("!f", msg)
    threshold = unp_msg[0]
    dig_threshold_str = "; Threshold value: " + str(threshold)
    return dig_threshold_str


def _get_volt_input_type_str(input_type):
    if 0 == input_type:
        msg = "Voltage"
    elif 1 == input_type:
        msg = "Gauge"
    elif 2 == input_type:
        msg = "Thermistor"
    elif 3 == input_type:
        msg = "Current"
    elif 4 == input_type:
        msg = "PTC"
    elif 5 == input_type:
        msg = "Potentiometer"
    elif 6 == input_type:
        msg = "Volt4v5"
    else:
        msg = "Unknown (%u)" % input_type
    return msg


def _get_volt_output_power_str(output_power):
    if 0 == output_power:
        msg = "0V"
    elif 1 == output_power:
        msg = "12V"
    elif 2 == output_power:
        msg = "24V"
    else:
        msg = "Unknown (%u)" % output_power
    return msg


def _get_volt_data_str(msg):
    msg_len = len(msg)
    if 5 == msg_len:
        unpack_format = "!IB"
        num_channels = 0
    elif 9 == msg_len:
        unpack_format = "!IBBBH"
        num_channels = 1
    elif 13 == msg_len:
        unpack_format = "!IBBBHBBH"
        num_channels = 2
    elif 17 == msg_len:
        unpack_format = "!IBBBHBBHBBH"
        num_channels = 3
    elif 21 == msg_len:
        unpack_format = "!IBBBHBBHBBHBBH"
        num_channels = 4

    unp_msg = _struct.unpack(unpack_format, msg)

    volt_data_str = "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    enabled_channels_bitmap = unp_msg[1]
    volt_data_str += "; ChEnabled: " + "0x%02X" % (enabled_channels_bitmap)
    enabled_channels = []
    if 0x01 & enabled_channels_bitmap:
        enabled_channels.append(0)
    if 0x02 & enabled_channels_bitmap:
        enabled_channels.append(1)
    if 0x04 & enabled_channels_bitmap:
        enabled_channels.append(2)
    if 0x08 & enabled_channels_bitmap:
        enabled_channels.append(3)

    for i in range(0, num_channels):
        volt_data_str += "; Ch: %u" % (enabled_channels[i])
        volt_data_str += " [InputType: " + _get_volt_input_type_str(unp_msg[2 + 3 * i])
        reading = (unp_msg[2 + 3 * i + 1] << 16) | unp_msg[2 + 3 * i + 2]
        volt_data_str += "; Reading: " + "%u]" % (reading)

    return volt_data_str


def _get_sipi_data_str(msg):

    msg_header = _struct.unpack("!IBB", msg[:6])

    sipi_data_str = "; Time: %u (%s)" % (msg_header[0], _second_to_time_iso8601(msg_header[0]))

    sipi_data_str += "; Sensors on the chain: " + "%u" % ((msg_header[1] & 0xF8) >> 3)

    sensor_types = msg_header[1] & 0x07
    sipi_data_str += "; Type of sensors:"
    if 0 == sensor_types:
        sipi_data_str += " Uniaxial "
    elif 1 == sensor_types:
        sipi_data_str += " Biaxial "
    else:
        sipi_data_str += " Error "

    sipi_data_str += "; EOD: " + "%u" % ((msg_header[2] & 0x80) >> 7)

    num_sensors_msg = (msg_header[2] & 0x70) >> 4
    sipi_data_str += "; NumSensorsMsg: " + "%u" % (num_sensors_msg)
    num_msg = msg_header[2] & 0x0F
    sipi_data_str += "; NumMsg: " + "%u" % (num_msg)

    bitoffset = 0

    for i in range(0, num_sensors_msg):
        sipi_data_str += "; Sensor Number: %d [" % (i + (num_msg - 1) * 4)
        a_axis = _extract_bits_from_array(msg[6:], bitoffset, 24)
        sipi_data_str += "Aaxis reading: %u" % (a_axis)
        bitoffset = bitoffset + 24

        temperature = _extract_bits_from_array(msg[6:], bitoffset, 24)
        sipi_data_str += "; Temperature reading: %u" % (temperature)
        bitoffset = bitoffset + 24

        if 1 == sensor_types:  # Only Biaxial
            b_axis = _extract_bits_from_array(msg[6:], bitoffset, 24)
            sipi_data_str += "; Baxis reading: %u" % (b_axis)
            bitoffset = bitoffset + 24
        sipi_data_str += "] "

    return sipi_data_str


def _get_volt_ch_config_str(msg):
    warmup_units_mask = 0xFE00
    unp_msg = _struct.unpack("!BBBHBBHBBHBBH", msg)
    volt_ch_config_str = "; ChEnBitmap: " + "0x%02X" % (unp_msg[0])
    for i in range(0, 4):
        volt_ch_config_str += "; Ch: %u" % (i)
        volt_ch_config_str += " [InType: " + _get_volt_input_type_str(unp_msg[1 + 3 * i + 0])
        volt_ch_config_str += "; OutPow: " + _get_volt_output_power_str(unp_msg[1 + 3 * i + 1])
        warmup_value = unp_msg[1 + 3 * i + 2]
        if (warmup_value & warmup_units_mask) == warmup_units_mask:
            warmup_units = "s"
            warmup_value = warmup_value & ~warmup_units_mask
        else:
            warmup_units = "ms"

        volt_ch_config_str += "; Warmup: " + "%u %s]" % (warmup_value, warmup_units)
    return volt_ch_config_str


def _get_sipi_config_str(msg):
    unp_msg = _struct.unpack("!BBB", msg)
    sipi_config_str = "; Enabled: %u" % (unp_msg[0] & 0x01)

    sipi_config_str += "; Number of sensors: %u" % (unp_msg[1] & 0x1F)

    sensor_type = unp_msg[2] & 0x01
    if 0 == sensor_type:
        type_value = "Uniaxial"
    elif 1 == sensor_type:
        type_value = "Biaxial"
    else:
        type_value = "Unknown"

    sipi_config_str += "; Type of sensors: " + type_value

    return sipi_config_str


# Tell appart volt config messages between:
#  - Original mode
#  - Sipi mode
def _get_volt_sipi_config_str(msg):
    volt_mode_mask = 0x60
    unp_msg = _struct.unpack("!B", msg[:1])
    mode = (unp_msg[0] & volt_mode_mask) >> 5
    if 0 == mode:  # original
        type_msg_str = "Volt Ch Config" + _get_volt_ch_config_str(msg)
    elif 1 == mode:  # Sipi
        type_msg_str = "Sipi Config" + _get_sipi_config_str(msg)
    return type_msg_str


def _get_pnode_input_type_str(input_type):
    if 0 == input_type:
        msg = "Gauge"
    elif 1 == input_type:
        msg = "Potentiometer"
    elif 2 == input_type:
        msg = "Volt Single Ended"
    elif 3 == input_type:
        msg = "Volt Differential"
    else:
        msg = "Unknown (%u)" % input_type
    return msg


def _get_pnode_data_str(msg):
    """Get a Pnode data message

    Pnode has two channels:
        Channel 1 can be Potentiometer or Gauge
        Channel 2 is always Thermistor
        Channel 3 is always Pulse counter
    """
    # First we get all data that is always present:
    #   Timestamp (I)
    #   Temperature (B)
    #   ChEnBitMap (B)
    node_data = _struct.unpack("!IbB", msg[:6])
    msg = msg[6:]

    pnode_data_str = "; Time: %u (%s)" % (node_data[0], _second_to_time_iso8601(node_data[0]))
    pnode_data_str += "; Temperature: %d" % (node_data[1])
    enabled_channels_bitmap = node_data[2]
    pnode_data_str += "; ChEnabled: " + "0x%02X" % (enabled_channels_bitmap)

    # Now we process Enabled channels
    # CH0 - (1 + 3) Byte
    if enabled_channels_bitmap == 0x01:
        unpack_format = "!BBH"
    # CH1 - (3) Byte
    elif enabled_channels_bitmap == 0x02:
        unpack_format = "!BH"
        offset_ch1 = 0
    # CH2 - (4) Byte
    elif enabled_channels_bitmap == 0x04:
        unpack_format = "!I"
        offset_ch2 = 0
    # CH0 & CH1 - (1 + 3 + 3) Byte
    elif enabled_channels_bitmap == 0x03:
        unpack_format = "!BBHBH"
        offset_ch1 = 3
    # CH0 & CH2 - (1 + 3 + 4) Byte
    elif enabled_channels_bitmap == 0x05:
        unpack_format = "!BBHI"
        offset_ch2 = 3
    # CH1 & CH2 - (3 + 4) Byte
    elif enabled_channels_bitmap == 0x06:
        unpack_format = "!BHI"
        offset_ch1 = 0
        offset_ch2 = 2
    # CH0 & CH1 & CH2 - (1 + 3 + 3 + 4) Byte
    elif enabled_channels_bitmap == 0x07:
        unpack_format = "!BBHBHI"
        offset_ch1 = 3
        offset_ch2 = 5

    if enabled_channels_bitmap != 0x00:
        unp_msg = _struct.unpack(unpack_format, msg)

    # If CH0
    if 0x01 & enabled_channels_bitmap:
        pnode_data_str += "; Ch: %u" % (0)
        pnode_data_str += " [InputType: " + _get_pnode_input_type_str(unp_msg[0])
        reading = (unp_msg[1] << 16) | unp_msg[2]
        pnode_data_str += "; Reading: " + "%u]" % (reading)
    # If CH1
    if 0x02 & enabled_channels_bitmap:
        pnode_data_str += "; Ch: %u" % (1)
        pnode_data_str += " [InputType: " + "Thermistor"
        reading = (unp_msg[0 + offset_ch1] << 16) | unp_msg[1 + offset_ch1]
        pnode_data_str += "; Reading: " + "%u]" % (reading)
    # If CH2
    if 0x04 & enabled_channels_bitmap:
        pnode_data_str += "; Ch: %u" % (2)
        pnode_data_str += " [InputType: " + "Pulse Counter"
        reading = unp_msg[0 + offset_ch2]
        pnode_data_str += "; Reading: " + "%u]" % (reading)

    return pnode_data_str


def _get_pnode_ch_config_str(msg):
    unp_msg = _struct.unpack("!BBHH", msg)
    pnode_ch_config_str = "; ChEnBitmap: " + "0x%02X" % (unp_msg[0])
    # Channel 0
    pnode_ch_config_str += "; Ch: %u" % (0)
    pnode_ch_config_str += " [InType: " + _get_pnode_input_type_str(unp_msg[1])
    pnode_ch_config_str += "; Warmup: " + "%u]" % unp_msg[2]

    # Channel 1
    pnode_ch_config_str += "; Ch: %u" % (1)
    pnode_ch_config_str += " [InType: " + "Thermistor"
    pnode_ch_config_str += "; Warmup: " + "%u]" % unp_msg[3]

    # Channel 1
    pnode_ch_config_str += "; Ch: %u" % (2)
    pnode_ch_config_str += " [InType: " + "%s]" % "Pulse Counter"

    return pnode_ch_config_str


def _get_laser_data_str(msg):
    """Get a Laser data message"""
    msg_decoder_dict = {
        "timestamp": {"position": 0, "bits": 32},
        "version": {"position": 32, "bits": 2},
        "reserved": {"position": 34, "bits": 2},
        "gain": {"position": 36, "bits": 1},
        "signalStrength": {"position": 37, "bits": 24},
        "temperature": {
            "position": 61,
            "bits": 11,
            "function": lambda msg, value: float(_uint_to_int(value, msg["bits"])) / 10.0,
        },
        "distance": {
            "position": 72,
            "bits": 24,
            "function": lambda msg, value: value / 10000.0,
        },  # Change units of the distance from 10/mm to m.
    }

    readings = {}
    for msg_type, proc_info in msg_decoder_dict.items():
        value = _extract_bits_from_array(msg, proc_info["position"], proc_info["bits"])
        # Ensure all the values are valid, if not replace the value with the error string.
        if "function" in proc_info:
            function = proc_info.get("function")
            readings[msg_type] = function(proc_info, value)
        else:
            readings[msg_type] = value

    laser_data_str = "; Time: %u (%s)" % (
        readings["timestamp"],
        _second_to_time_iso8601(readings["timestamp"]),
    )
    # Get version
    laser_data_str += "; Version: {}".format(readings["version"])

    # First parse everthing then print it since we will change order

    laser_data_str += "; Distance: {}".format(readings["distance"])  # From 10/mm to meters
    laser_data_str += "; Temperature: {}".format(readings["temperature"])
    laser_data_str += "; Gain: {}".format(readings["gain"])
    laser_data_str += "; SignalStrength: {}".format(readings["signalStrength"])

    return laser_data_str


def _get_lora_addr_config_str(msg):
    unp_msg = _struct.unpack("!I", msg)
    addr = unp_msg[0]
    lora_addr_config_str = "; Address: " + str(addr)
    return lora_addr_config_str


def _get_lora_netid_config_str(msg):
    unp_msg = _struct.unpack("!I", msg)
    addr = unp_msg[0]
    lora_addr_config_str = "; NetworkID: " + str(addr)
    return lora_addr_config_str


def _get_lora_slot_time_config_str(msg):
    unp_msg = _struct.unpack("!H", msg)
    slot_time = unp_msg[0]
    lora_slot_time_config_str = "; SendSlotTime: " + str(slot_time)
    return lora_slot_time_config_str


def _get_sampling_period_and_slot_time_agg_config_str(msg):
    unp_msg = _struct.unpack("!BHH", msg)
    sampling_period = (unp_msg[0] << 16) | unp_msg[1]
    agg_config_str = "; SamplingPeriod: " + str(sampling_period)
    slot_time = unp_msg[2]
    agg_config_str += "; SendSlotTime: " + str(slot_time)
    return agg_config_str


def _get_lora_general_config_str(msg):
    unp_msg = _struct.unpack("!BBBBIH", msg)
    msg_version = (unp_msg[0] & 0xF0) >> 4
    lora_general_config_str = "; Msg Version: %u" % msg_version
    mac_version = unp_msg[0] & 0x0F
    lora_general_config_str += "; MAC Version: %u" % mac_version
    lora_general_config_str += "; Use500kHzCh: " + str((unp_msg[1] & 0x80) == 0x80)
    lora_general_config_str += "; RadioEnabled: " + str((unp_msg[1] & 0x40) == 0x40)
    lora_general_config_str += "; ETSIEnabled: " + str((unp_msg[1] & 0x20) == 0x20)
    lora_general_config_str += "; ADREnabled: " + str((unp_msg[1] & 0x10) == 0x10)
    lora_general_config_str += "; SF: %u" % (unp_msg[1] & 0x0F)
    lora_general_config_str += "; TxPower: %u" % (unp_msg[2])
    if msg_version == 1:
        lora_general_config_str += "; ChDcEnabled: " + str((unp_msg[3] & 0x20) == 0x20)
    lora_general_config_str += "; UseRx2: " + str((unp_msg[3] & 0x10) == 0x10)
    lora_general_config_str += "; Rx2SF: %u" % (unp_msg[3] & 0x0F)
    lora_general_config_str += "; Rx2Freq: %u" % (unp_msg[4])
    lora_general_config_str += "; SlotTime: %u" % (unp_msg[5])
    return lora_general_config_str


def _get_lora_join_config_str(msg):
    unp_msg = _struct.unpack("!BBBBBBBBBBBBBBBBBHBBBB", msg)
    lora_join_config_str = "; Msg Version: %u" % unp_msg[0]
    lora_join_config_str += "; DevEUI: "
    for i in range(1, 1 + 8):
        lora_join_config_str += "%02X" % unp_msg[i]
    lora_join_config_str += "; AppEUI: "
    for i in range(9, 9 + 8):
        lora_join_config_str += "%02X" % unp_msg[i]
    lora_join_config_str += "; MaxTimeWithoutDownlinkInMin: %u" % unp_msg[17]
    lora_join_config_str += "; JoinRetryMaxTimeDivisor: %u (24h/(x+1))" % unp_msg[18]
    join_retry_min_time_multiply = (unp_msg[19] & 0xFC) >> 2
    lora_join_config_str += (
        "; JoinRetryMinTimeMultiply: %u (10s*(x+1))" % join_retry_min_time_multiply
    )
    join_retry_multiplier_when_fail = (unp_msg[19] & 0x03) >> 0
    lora_join_config_str += (
        "; JoinRetryMultiplierWhenFail: %u (*(x+1))" % join_retry_multiplier_when_fail
    )
    lora_join_config_str += "; MaxNumLinkChecksSendBeforeReconnect: %u" % unp_msg[20]
    activation = (unp_msg[21] & 0x80) >> 7
    if activation == 0:
        activation = "ABP"
    else:
        activation = "OTAA"
    framecntmode = (unp_msg[21] & 0x40) >> 6
    if framecntmode == 0:
        framecntmode = "16b"
    else:
        framecntmode = "32b"
    lora_join_config_str += "; Activation: %s" % activation
    lora_join_config_str += "; FrameCntMode: %s" % framecntmode
    return lora_join_config_str


def _get_lora_ch_config_str(msg, group):
    unp_msg = _struct.unpack("!BBIIIIIIII", msg)
    version = (unp_msg[0] & 0xF0) >> 4
    lora_ch_config_str = "; Version: %u" % version
    ch_type = unp_msg[0] & 0x0F
    lora_ch_config_str += "; ChType: %u" % ch_type
    lora_ch_config_str += "; EnabledMap: 0x%x" % unp_msg[1]

    if 1 == version:
        channels = [
            "Ch%u: %u (%02x)"
            % (8 * group + i, (unp_msg[i + 2] & 0x00FFFFFF) * 100, unp_msg[i + 2] >> 24)
            for i in range(8)
        ]
    else:
        channels = ["Ch%u: %u" % (8 * group + i, unp_msg[i + 2]) for i in range(8)]

    lora_ch_config_str += "; " + "; ".join(channels)
    return lora_ch_config_str


def _get_response_str(msg):
    unp_msg = _struct.unpack("!H", msg)
    response = unp_msg[0]
    if response == 0:
        response_str = "OK"
    elif response == 1:
        response_str = "ERR_INVALID_MSG_SIZE"
    elif response == 2:
        response_str = "ERR_INVALID_PARAMETER"
    elif response == 3:
        response_str = "ERR_RESET"
    elif response == 4:
        response_str = "ERR_NO_CONFIG"
    elif response == 5:
        response_str = "ERR_UNKNOWN_COMMAND"
    elif response == 6:
        response_str = "ERR_NOT_SUPPORTED"
    elif response == 7:
        response_str = "ERR_CMD_FAILED"
    elif response == 127:
        response_str = "RESTART_RECOVERY"
    elif response == 128:
        response_str = "END_OF_DATA_RECOVERY"
    elif response == 129:
        response_str = "END_OF_LORA_COV_TEST"
    else:
        response_str = "Unknown: %u" % (response)
    return response_str


def _get_health_str(msg):
    unp_msg = _struct.unpack("!IIHbHBB", msg)
    msg_str = "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    msg_str += "; Uptime: %u" % (unp_msg[1])
    msg_str += "; Battery: %d" % (unp_msg[2])
    msg_str += "; Temperature: %d" % (unp_msg[3])
    msg_str += "; SN: %u; " % (unp_msg[4])
    msg_str += "; FW: %02d.%02d " % (unp_msg[5], unp_msg[6])
    return msg_str


def _get_health_v2_str(msg):
    unp_msg = _struct.unpack("!IIHbHBBH", msg)
    msg_str = "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    msg_str += "; Uptime: %u" % (unp_msg[1])
    msg_str += "; Battery: %d" % (unp_msg[2])
    msg_str += "; Temperature: %d" % (unp_msg[3])
    msg_str += "; SN: %u; " % (unp_msg[4])
    msg_str += "; FW: %02d.%02d " % (unp_msg[5], unp_msg[6])
    delta = unp_msg[7]
    if delta > 0x7FF:
        units = "minutes"
        delta = delta - 0x8000
    else:
        units = "seconds"
    msg_str += "; Delta: %d %s " % (delta, units)
    return msg_str


def _get_health_v3_str(msg):
    unp_msg = _struct.unpack("!IIHBHBBH", msg)
    version = unp_msg[1] >> 30
    uptime = unp_msg[1] & 0x3FFFFFFF
    msg_str = "; Version: %u" % (version)
    msg_str += "; Time: %u (%s)" % (unp_msg[0], _second_to_time_iso8601(unp_msg[0]))
    msg_str += "; Uptime: %u" % (uptime)

    bat_v = unp_msg[2] >> 4
    bat_v *= (
        10  # give the battery voltage value in milli volts to remain consistent with HealthMsgV2
    )
    temp = ((unp_msg[2] & 0x0F) << 4) + (unp_msg[3] >> 4)
    temp = (temp ^ 0x80) - 0x80  # interpret temp as a 8bit signed value
    serial_hi = unp_msg[3] & 0x0F
    serial = (serial_hi << 16) + unp_msg[4]

    msg_str += "; Battery: %d" % (bat_v)
    msg_str += "; Temperature: %d" % (temp)
    msg_str += "; SN: %u " % (serial)
    msg_str += "; FW: %02d.%02d " % (unp_msg[5], unp_msg[6])
    delta = unp_msg[7]
    if delta > 0x7FF:
        units = "minutes"
        delta = delta - 0x8000
    else:
        units = "seconds"
    msg_str += "; Delta: %d %s " % (delta, units)
    return msg_str


def _get_recover_data(msg):
    mote_id_lower_16 = NODEID & 0xFFFF  # Mask the frist 16 bits
    most_significant_4 = (NODEID >> 16) & 0x0F  # Extract bits 16 to 20 (4 bits)
    # Construct the first byte (header + 4 lower bits from NODEID)
    first_byte = 0x40 | most_significant_4
    # Construct the dummy header
    dummy_header_bytes = (
        bytes([first_byte])  # First byte with NODEID bits
        + bytes([PRCODE])  # PRCODE (1 byte)
        + mote_id_lower_16.to_bytes(2, byteorder="big")  # Last 16 bits of NODEID
        + b"\xf8"  # needed for the parsing lib, as here we don't have this part of the message
    )
    unp_msg = _struct.unpack("!BB", msg[:2])
    data_type = unp_msg[1]
    msg_str = "; CaptureId: %u; " % (unp_msg[0])
    decoded_msg_str = _get_type_msg_str(data_type, msg[2:])
    if "Unknown" in decoded_msg_str:  # TODO: This should be implemented in the parsing library.
        try:
            json_msg = msg2json(
                dummy_header_bytes + msg[1:]
            )  # we skip the capture id to allow a message to be parsed
            decoded_msg_str = _json2string(json_msg)
        except Exception:
            print("ERROR unpacking message")

    return msg_str + decoded_msg_str


def _get_interval_data(msg):
    unp_msg = _struct.unpack("!II", msg)
    msg_str = ": %u(%s)>%u(%s); " % (
        unp_msg[0],
        _second_to_time_iso8601(unp_msg[0]),
        unp_msg[1],
        _second_to_time_iso8601(unp_msg[1]),
    )
    return msg_str


def _get_lora_session_str(msg):
    unp_msg = _struct.unpack("!BBHBBIIIIIBBBBBBBBBBBBBBBBHH", msg)

    msg_str = "; State: %u" % (unp_msg[0] >> 5)
    state = int(unp_msg[0] >> 5)
    if state == 0:
        msg_str += " (INVALID)"
    elif state == 1:
        msg_str += " (JOINREQ_SENDING)"
    elif state == 2:
        msg_str += " (JOINRES_RECV)"
    elif state == 7:
        msg_str += " (ACTIVATED)"
    else:
        msg_str += " (UNKNOWN)"

    msg_str += "; ProtocolMin: %u" % (unp_msg[1])

    msg_str += "; DevNonce: %u" % (unp_msg[2])

    msg_str += "; DLSettings: %u" % (unp_msg[3])
    msg_str += "; RxDelay: %u" % (unp_msg[4])

    msg_str += "; DevAddr: %u" % (unp_msg[5])
    msg_str += "; JoinNonce: %u" % (unp_msg[6])
    msg_str += "; HomeNetID: %u" % (unp_msg[7])
    msg_str += "; FCntUP: %u" % (unp_msg[8])
    msg_str += "; FCntDown: %u" % (unp_msg[9])

    msg_str += "; CFList: "
    for i in range(10, 10 + 16):
        msg_str += "%02X" % (unp_msg[i])
    msg_str += "; AppSKey: %04X" % (unp_msg[26])
    msg_str += "; NwkSEncKey: %04X" % (unp_msg[27])
    return msg_str


def _get_node_info(msg):
    unp_msg = _struct.unpack("!HBBI", msg)
    msg_str = "; SN: %u; " % (unp_msg[0])
    msg_str += "; FW: %02d.%02d " % (unp_msg[1], unp_msg[2])
    msg_str += "; BuildTime: %s " % _second_to_time_iso8601(unp_msg[3])
    return msg_str


def _get_node_infov2(msg):
    unp_msg = _struct.unpack("!BIBBI", msg)
    version = unp_msg[0]
    msg_str = "; Version: %u; " % (version)
    msg_str += "; SN: %u; " % (unp_msg[1])
    msg_str += "; FW: %02d.%02d " % (unp_msg[2], unp_msg[3])
    msg_str += "; BuildTime: %s " % _second_to_time_iso8601(unp_msg[4])
    return msg_str


def _get_debug_info_assert_str(msg):
    num_line, file_name, charsum = _struct.unpack("!H20sB", msg)
    msg_str = "; Line: %u; File: %s; Charsum: %u" % (num_line, file_name.decode("utf-8"), charsum)
    return msg_str


def _get_debug_info_task_name_str(msg):
    task_name = _struct.unpack("!15s", msg)
    msg_str = "; Task Name: %s" % (task_name[0].decode("utf-8"))
    return msg_str


def _get_debug_info_str(msg):
    version_and_type, timestamp = _struct.unpack("!BI", msg[:5])
    version = (version_and_type & 0xC0) >> 6
    if 0 != version:
        msg_str = "; Unsupported Message version (%u)" % (version)
    else:
        msg_type = version_and_type & 0x3F
        msg_str = "; Time: %u (%s)" % (timestamp, _second_to_time_iso8601(timestamp))
        if msg_type == 1:
            msg_str += "; ASSERT" + _get_debug_info_assert_str(msg[5:])
        elif msg_type == 2:
            msg_str += "; Stack Overflow" + _get_debug_info_task_name_str(msg[5:])
        elif msg_type == 3:
            msg_str += "; Watchdog" + _get_debug_info_task_name_str(msg[5:])
        else:
            msg_str += "; Unknown type (%u)" % (msg_type)
    return msg_str


def _get_extended_node_info(msg):
    unp_msg = _struct.unpack("!BBBBB", msg)
    msg_str = "; MsgVersion: %u; HW: PCB1 v%u.%u, PCB2 v%u.%u" % (
        unp_msg[0],
        unp_msg[1],
        unp_msg[2],
        unp_msg[3],
        unp_msg[4],
    )
    return msg_str


def _get_geoflex_dig_custom_cmd_str(msg):
    msg_payload = _struct.unpack("!BBB", msg)

    cust_cmd_str = "; Command report:"
    cust_cmd_str += " Cmd Code: %u" % (msg_payload[0])
    cust_cmd_str += "; Cmd result: %u" % (msg_payload[1])
    cust_cmd_str += "; Cmd data: %u" % (msg_payload[2])

    return cust_cmd_str


def _get_measurand_dig_custom_cmd_str(msg):
    msg_payload = _struct.unpack("!BBBH", msg)

    cust_cmd_str = "; Command report:"
    cust_cmd_str += " Cmd Code: %u" % (msg_payload[0])
    cust_cmd_str += "; Cmd result: %u" % (msg_payload[1])
    cust_cmd_str += "; Protocol configured: %u" % (msg_payload[2])
    cust_cmd_str += "; Number of sensors detected: %u" % (msg_payload[3])

    return cust_cmd_str


def _get_dig_custom_cmd(msg):
    payload_str = ""
    msg_hdr = _struct.unpack("!BB", msg[:2])
    sensor_type = msg_hdr[0]
    dig_res_code = msg_hdr[1]

    dig_cust_cmd_str = "; Dig error: %u" % (dig_res_code)

    if dig_res_code == 0:  # No error reported by the main module
        if sensor_type == 0:
            payload_str = "; GSI Cust Cmd"
            pass
        elif sensor_type == 1:
            payload_str = "; Sisgeo Legacy Cust Cmd"
            pass
        elif sensor_type == 2:
            payload_str = "; MDT Cust Cmd"
            pass
        elif sensor_type == 3:
            payload_str = "; Sisgeo V3 Cust Cmd"
            pass
        elif sensor_type == 4:
            payload_str = "; Geoflex Cust Cmd"
            payload_str += _get_geoflex_dig_custom_cmd_str(msg[2:])
        elif sensor_type == 5:
            payload_str = "; Generic Modbus Cust Cmd"
            pass
        elif sensor_type == 6:
            payload_str = "; Measurand Cust Cmd"
            payload_str += _get_measurand_dig_custom_cmd_str(msg[2:])
        elif sensor_type == 8:
            payload_str = "; Extended Measurand Cust Cmd"
            payload_str += _get_measurand_dig_custom_cmd_str(msg[2:])
        else:
            payload_str = "; Unknown sensor type (%u)" % (msg_hdr[0])

    return dig_cust_cmd_str + payload_str


def _get_type_msg_str(msg_type, msg):
    if msg_type == 0:
        type_msg_str = "Response " + _get_response_str(msg)
    elif msg_type == 1:
        type_msg_str = "Recover Data " + _get_recover_data(msg)
    elif msg_type == 2:
        type_msg_str = "Interval Data " + _get_interval_data(msg)
    elif msg_type == 3:
        type_msg_str = "Node Info " + _get_node_info(msg)
    elif msg_type == 5:
        type_msg_str = "Extended node Info " + _get_extended_node_info(msg)
    elif msg_type == 6:
        type_msg_str = "Lora Session" + _get_lora_session_str(msg)
    elif msg_type == 7:
        type_msg_str = "Dig Custom Command" + _get_dig_custom_cmd(msg)
    elif msg_type == 9:
        type_msg_str = "Node Info V2 " + _get_node_infov2(msg)
    elif msg_type == 10:
        type_msg_str = "Tilt360A Alert Message" + _get_t360a_alert_str(msg)
    elif msg_type == 21:
        type_msg_str = "Get Misc Test Commands Status" + _get_misc_cmd_status_str(msg)
    elif msg_type == 22:
        type_msg_str = "Reception Opportuninty Data " + _get_reception_opportunity_str(msg)
    elif msg_type == 23:
        type_msg_str = "Debug info " + _get_debug_info_str(msg)
    elif msg_type == 63:
        type_msg_str = "Printf: " + str(msg)
    elif msg_type == 64:
        type_msg_str = "Health " + _get_health_str(msg)
    elif msg_type == 65:
        type_msg_str = "VW " + _get_vw_data_str(msg)
    elif msg_type == 66:
        type_msg_str = "GSI " + _get_gsi_data_str(msg)
    elif msg_type == 67:
        type_msg_str = "Volt " + _get_volt_data_str(msg)
    elif msg_type == 68:
        type_msg_str = "Dig " + _get_dig_data_str(msg)
    elif msg_type == 69:
        type_msg_str = "Tilt " + _get_tilt_data_str(msg)
    elif msg_type == 70:
        type_msg_str = "Health-v2 " + _get_health_v2_str(msg)
    elif msg_type == 71:
        type_msg_str = "Pnode " + _get_pnode_data_str(msg)
    elif msg_type == 72:
        type_msg_str = "Sipi " + _get_sipi_data_str(msg)
    elif msg_type == 73:
        type_msg_str = "Laser " + _get_laser_data_str(msg)
    elif msg_type == 74:
        type_msg_str = "Vw magnitude " + _get_vw_magnitude_data_str(msg)
    #elif msg_type == 75:
    #    type_msg_str = "Generic Modbus " + _get_gm_data_str(msg)
    # elif msg_type == 76:  # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "Tilt360 " + _get_tilt360_data_str(msg)
    # elif msg_type == 77:  # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "Tilt360 raw" + _get_tilt360_raw_data_str(msg)
    elif msg_type == 78:
        type_msg_str = "Laser360 " + _get_laser360_data_str(msg)
    # elif msg_type == 79:  # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "Health-v3 " + _get_health_v3_str(msg)
    # elif msg_type == 80: # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "Tilt360A Data " + _get_tilt360alert_data_str(msg)
    elif msg_type == 81:  # Used for the multihop GW repeater health message.
        raise NotImplementedError()  # implemented in the ls-message-parser library
    # elif msg_type == 128: # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "VW5 Config" + _get_vw_config_str(msg)
    elif msg_type == 129:
        type_msg_str = "GSI Ch Config" + _get_gsi_ch_config_str(msg)
    elif msg_type == 130:
        type_msg_str = "SP Config" + _get_sp_config_str(msg)
    elif msg_type == 131:
        type_msg_str = "LoRa Addr Config" + _get_lora_addr_config_str(msg)
    elif msg_type == 132:
        type_msg_str = "LoRa General Config" + _get_lora_general_config_str(msg)
    elif msg_type == 133:
        type_msg_str = "LoRa Ch Grp0 Config" + _get_lora_ch_config_str(msg, 0)
    elif msg_type == 134:
        type_msg_str = "LoRa Ch Grp1 Config" + _get_lora_ch_config_str(msg, 1)
    elif msg_type == 142:
        type_msg_str = "LoRa Ch FCC Down Config" + _get_lora_ch_config_str(msg, 0)
    elif msg_type == 141:
        type_msg_str = "LoRa NetID Config" + _get_lora_netid_config_str(msg)
    elif msg_type == 143:
        type_msg_str = _get_volt_sipi_config_str(msg)
    elif msg_type == 144:
        type_msg_str = "LoRa Slot Time Config" + _get_lora_slot_time_config_str(msg)
    elif msg_type == 145:
        type_msg_str = "Dig Ch Config" + _get_dig_ch_config_str(msg)
    elif msg_type == 146:
        type_msg_str = "Tilt Ch Config" + _get_tilt_ch_calib_str(msg)
    elif msg_type == 147:
        type_msg_str = "Pnode Ch Config" + _get_pnode_ch_config_str(msg)
    elif msg_type == 148:
        type_msg_str = "Lora Join Config" + _get_lora_join_config_str(msg)
    elif msg_type == 149:
        type_msg_str = "Supply Threshold Config" + _get_supply_threshold_str(msg)
    elif msg_type == 150:
        type_msg_str = "VW Magnitude Threshold" + _get_vw_magnitude_threshold_str(msg)
    elif msg_type == 151:
        type_msg_str = "Generic Modbus Instructions Config" + _get_gmm_instructions_cfg(msg)
    # elif msg_type == 152: # Commented this so that ls message parsing lib will be called always for decode msg
    #     type_msg_str = "Tilt360 Ch Config" + _get_tilt360_ch_calib_str(msg)
    elif msg_type == 153:
        type_msg_str = "Laser360 Ch Config" + _get_laser360_ch_config_str(msg)
    elif msg_type == 154:
        type_msg_str = "Tilt360 Ch Config" + _get_tilt360_ch_config_str(msg)
    elif msg_type == 155:
        type_msg_str = "Tilt360A Ch Config" + _get_tilt360alert_ch_config_str(msg)
    elif msg_type == 156:
        type_msg_str = "Tilt360A SP Config" + _get_t360a_sp_alert_config_str(msg)
    elif msg_type == 157:
        type_msg_str = "Get Sampling Scheduler Config" + _get_sampling_scheduler_cfg_str(msg)
    elif msg_type == 192:
        type_msg_str = "SP and ST AggConfig" + _get_sampling_period_and_slot_time_agg_config_str(
            msg
        )
    elif msg_type == 193:
        type_msg_str = (
            "Set Tilt360 Ch and Tilt360A Alert SP AggConfig"
            + _get_tilt360alert_ch_config_sp_alert_aggcfg_str(msg)
        )
    else:
        type_msg_str = "Unknown   "

    return type_msg_str


# TODO at some point we will jump to prioritize the parsing library,
# but currently the output format is nicer/shorter with the old parsing
def msg2string(msg):
    return _msg2string_priority_old_parsing(msg)
    # return _msg2string_priority_parsing_library(msg)


def _msg2string_priority_old_parsing(msg):
    try:
        out_str = _msg2string_old(msg)
        if "; Unknown" in out_str:
            raise Exception
        return out_str
    except Exception:
        pass
    try:
        return _msg2string_with_parsing_library(msg)
    except Exception:
        print("ERROR unpacking message")


def _msg2string_priority_parsing_library(msg):
    try:
        return _msg2string_with_parsing_library(msg)
    except Exception:
        pass
    try:
        out_str = _msg2string_old(msg)
        return out_str
    except Exception:
        print("ERROR unpacking message")


def _get_old_string_header_from_msg(msg):
    msg_str = ""

    unp_header_and_type = _struct.unpack("!BBHBB", msg[:6])

    if (unp_header_and_type[0] & 0x40) != 0x40:
        _logging.error("Invalid header")
        raise Exception
    else:

        prcode = unp_header_and_type[1]
        mote_id = ((unp_header_and_type[0] & 0x0F) << 16) + unp_header_and_type[2]
        num_seq = unp_header_and_type[3]

        msg_str = (
            "PrCode: " + str(prcode) + "; ID: " + str(mote_id) + "; #Seq: " + str(num_seq) + "; "
        )

    return msg_str


def _msg2string_with_parsing_library(msg):
    # TODO To keep the format more similar we keep the old header.
    # Plus at this moment the seq number is not parsed by the parsing library.
    header = _get_old_string_header_from_msg(msg)
    json_msg = msg2json(msg)
    msg_type = json_msg.pop("type")
    if msg_type:
        header += f"{msg_type}; "
    return header + _json2string(json_msg, msg_type=msg_type)


def set_prcode_nodeid(prcode, moteid):
    global PRCODE, NODEID
    PRCODE = prcode
    NODEID = moteid


def _msg2string_old(msg):
    msg_str = ""
    try:
        unp_header_and_type = _struct.unpack("!BBHBB", msg[:6])

        if (unp_header_and_type[0] & 0x40) != 0x40:
            _logging.error("Invalid header")
        else:
            prcode = unp_header_and_type[1]
            mote_id = ((unp_header_and_type[0] & 0x0F) << 16) + unp_header_and_type[2]
            set_prcode_nodeid(prcode, mote_id)
            num_seq = unp_header_and_type[3]

            type_msg_str = _get_type_msg_str(unp_header_and_type[4], msg[6:])

            msg_str = (
                "PrCode: "
                + str(prcode)
                + "; ID: "
                + str(mote_id)
                + "; #Seq: "
                + str(num_seq)
                + "; "
                + type_msg_str
            )

    except _struct.error:
        print("ERROR unpacking message")
        _logging.error("Parsing msg")
        msg_str = ""
        for i in msg:
            msg_str += "%02x " % (ord(i))
        _logging.debug(msg_str)

    return msg_str


def _camel_case(s):
    s = _sub(r"(_)+", " ", s).title().replace(" ", "")
    return "".join([s[0].lower(), s[1:]])


def _msg2json_old(binary_msg):
    """
    Examples:
        PrCode: 73; ID: 5451; #Seq: 3; LoRa Slot Time Config; SendSlotTime: 10
        PrCode: 73; ID: 5451; #Seq: 5; LoRa General Config; Msg Version: 0; MAC Version: 0; Use500kHzCh: False;
            RadioEnabled: True; ETSIEnabled: False; ADREnabled: False; SF: 11; TxPower: 14; UseRx2: False;
            Rx2SF: 12; Rx2Freq: 1020000000; SlotTime: 0
        PrCode: 80; ID: 51509; #Seq: 7; Tilt360A Ch Config; Version: 0; Reserved: 0; ChEn: [0,0,0];
            ChAlertEn: [0,0,0]; Absolute Threshold Alert Off Delay: 8; Absolute Threshold Axis 1: [Upper: 0, Lower: 0];
            Absolute Threshold Axis 2: [Upper: 0, Lower: 0]; Absolute Threshold Axis 3: [Upper: 0, Lower: 0]
        PrCode: 73; ID: 5451; #Seq: 22; Interval Data : 1(1970-01-01 01:00:01)>1653043200(2022-05-20 12:40:00);
        PrCode: 73; ID: 5451; #Seq: 4; Extended node Info ; MsgVersion: 0; HW: PCB1 v0.0, PCB2 v0.0
    """

    try:
        out_str = _msg2string_old(binary_msg)
        msg = {}
        for item in out_str.split(";"):
            if item == " ":
                pass
            elif item == "":
                pass
            elif ":" in item:
                key = item.split(":")[0]
                key = _camel_case(key)
                value = item.split(":")[1:]
                value = ":".join(value)
                if "," not in value:
                    # Normal case
                    value = _camel_case(value)
                    try:
                        value = int(value)
                    except Exception:
                        pass
                    msg[key] = value
                elif "[" not in value:
                    # when there is an array: PCB1 v0.0, PCB2 v0.0
                    msg[key] = value
                elif ":" not in value:
                    # when there is an array: [0,0,0]
                    msg[key] = literal_eval(value)
                else:
                    # when there is a dict: [Upper: 0, Lower: 0]
                    in_msg = {}
                    value = value.replace("[", "")
                    value = value.replace("]", "")
                    for in_item in value.split(","):
                        in_key = in_item.split(":")[0]
                        in_key = _camel_case(in_key)
                        in_value = in_item.split(":")[1]
                        in_value = _camel_case(in_value)
                        try:
                            in_value = int(in_value)
                        except Exception:
                            pass
                        in_msg[in_key] = in_value
                    msg[key] = in_msg
            else:
                msg["type"] = _camel_case(item)
    except Exception as e:
        _logging.error(e)
        print(e)
        raise NameError("Could not parse received message")

    return msg


def msg2json(binary_msg):
    msg = None
    # It will be required to pass radio metadata if no changes are done in the parsing library
    # meta = RadioMetadata.RadioMetadata(12345, "12345", 1547200203000, -73, 11, "ETSIV1", 68157505, 869.525, 7, "01")
    try:
        out = _decode_msg(binary_msg)
        msg = out.get_decoded_message_dict()
        # Hack to be able to differentiate health v2 and v3
        if msg["type"] == "healthV2":
            amtype = int(binary_msg[5])
            if amtype == 79:
                msg["type"] = "healthV3"
    except Exception:
        # _logging.error(binary_msg)
        # _logging.error(e)
        # raise NameError("Could not parse received message")
        pass
    if msg is None:
        msg = _msg2json_old(binary_msg)
    return msg


def _inmsg_get_config_str(msg):
    unp_msg = _struct.unpack("!B", msg)
    cfg_amtype = unp_msg[0]

    if cfg_amtype == 128:
        cfg_str = "VW"
    elif cfg_amtype == 129:
        cfg_str = "GSI_CH"
    elif cfg_amtype == 130:
        cfg_str = "SP"
    elif cfg_amtype == 131:
        cfg_str = "LORA_ADDR"
    elif cfg_amtype == 132:
        cfg_str = "LORA_GENERAL"
    elif cfg_amtype == 133:
        cfg_str = "LORA_CH0"
    elif cfg_amtype == 134:
        cfg_str = "LORA_CH1"
    elif cfg_amtype == 141:
        cfg_str = "LORA_KEYS"
    elif cfg_amtype == 142:
        cfg_str = "LORA_FCC_DOWN_CH"
    elif cfg_amtype == 143:
        cfg_str = "VOLT_CH"
    elif cfg_amtype == 144:
        cfg_str = "LORA_SLOT_TIME"
    elif cfg_amtype == 145:
        cfg_str = "DIG_CH"
    elif cfg_amtype == 146:
        cfg_str = "TILT_CH_CAL"
    elif cfg_amtype == 147:
        cfg_str = "PNODE_CH"
    elif cfg_amtype == 149:
        cfg_str = "SUPPLY_THRESHOLD"
    else:
        cfg_str = "Unknown: %u" % (cfg_amtype)
    return cfg_str


def _inmsg_recover_data_str(msg):
    unp_msg = _struct.unpack("!BII", msg)
    amtype = unp_msg[0]
    start = unp_msg[1]
    stop = unp_msg[2]

    recover_str = "; DataType: "
    if amtype == 0:
        recover_str += "All"
    elif amtype == 64:
        recover_str += "HEALTH_DATA"
    elif amtype == 65:
        recover_str += "VW_DATA"
    elif amtype == 66:
        recover_str += "GSI_DATA"
    elif amtype == 67:
        recover_str += "VOLT_DATA"
    elif amtype == 68:
        recover_str += "DIG_DATA"
    elif amtype == 69:
        recover_str += "TILT_DATA"
    elif amtype == 70:
        recover_str += "HEALTH_V2_DATA"
    elif amtype == 71:
        recover_str += "PNODE_DATA"

    recover_str += "; From %u(%s) to %u(%s)" % (
        start,
        _second_to_time_iso8601(start),
        stop,
        _second_to_time_iso8601(stop),
    )

    return recover_str


def _inmsg_set_time_str(msg):
    unp_msg = _struct.unpack("!I", msg)
    time_to_set = unp_msg[0]

    set_time_str = "; To %u(%s)" % (time_to_set, _second_to_time_iso8601(time_to_set))

    return set_time_str


def _inmsg_set_node_id_str(msg):
    unp_msg = _struct.unpack("!IH", msg)
    password = unp_msg[0]
    node_id = unp_msg[1]

    node_id_str = "; Password: %x; Node ID: %u" % (password, node_id)

    return node_id_str


def _inmsg_factory_reset_str(msg):
    unp_msg = _struct.unpack("!I", msg)
    password = unp_msg[0]

    factory_reset_str = "; Password: %x" % (password)

    return factory_reset_str


def _inmsg_lora_coverage_str(msg):
    unp_msg = _struct.unpack("!I", msg)
    token = unp_msg[0]

    lora_coverage_str = "; Token: %x" % (token)

    return lora_coverage_str


def _inmsg_set_lora_keys_config_str(msg):
    unp_msg = _struct.unpack("!IIIIIIIIIH", msg)
    appkey0 = unp_msg[0]
    appkey1 = unp_msg[1]
    appkey2 = unp_msg[2]
    appkey3 = unp_msg[3]
    netkey0 = unp_msg[4]
    netkey1 = unp_msg[5]
    netkey2 = unp_msg[6]
    netkey3 = unp_msg[7]
    addr = unp_msg[8]
    crc = unp_msg[9]
    lora_addr_config_str = (
        "; AppKey: %08x%08x%08x%08x; NetKey: %08x%08x%08x%08x; NetworkID: %u; CRC: %04x"
        % (appkey0, appkey1, appkey2, appkey3, netkey0, netkey1, netkey2, netkey3, addr, crc)
    )
    return lora_addr_config_str


def _get_misc_cmd_status_str(msg):

    command_id_string = {0: ["LoRa WAN Certifications Module", {0: "Disabled", 1: "Enabled"}]}
    msgver = _extract_bits_from_array(msg, 0, 4)
    reserved = _extract_bits_from_array(msg, 4, 4)
    cmd_id = _extract_bits_from_array(msg, 8, 8)
    cmd_resp = _extract_bits_from_array(msg, 16, 8)
    misc_cmd_status_str = "; MsgVersion: %u; Reserved: %u; Command ID: %u: %s; Status: %s" % (
        msgver,
        reserved,
        cmd_id,
        command_id_string[cmd_id][0],
        command_id_string[cmd_id][1][cmd_resp],
    )
    return misc_cmd_status_str


def _get_sampling_scheduler_cfg_str(msg):
    action_codes = [
        "NormalSample",
        "CommonAction1",
        "CommonAction2",
        "CommonAction3",
        "CommonAction4",
        "CommonAction5",
        "CommonAction6",
        "CommonAction7",
        "NodeAction1",
        "NodeAction2",
        "NodeAction3",
        "NodeAction4",
        "NodeAction5",
        "NodeAction6",
        "NodeAction7",
        "ExtendedAction",
    ]
    actions_with_payload = [
        "CommonAction4",
        "CommonAction5",
        "CommonAction6",
        "CommonAction7",
        "NodeAction4",
        "NodeAction5",
        "NodeAction6",
        "NodeAction7",
        "ExtendedAction",
    ]
    weekdays = ["Monday:", "Tuesday:", "Wednesday:", "Thursday:", "Friday:", "Saturday:", "Sunday:"]

    def parse_skipped_samples(msg, pos):
        result_str = "; NumSkippedSamples: "
        p = pos
        value = _extract_bits_from_array(msg, p, 8)
        p += 8
        result_str += str(value)
        return p, result_str

    def parse_action_payload(msg, pos):
        result_str = "; UnconventionalActionPayload: ["
        p = pos
        for _ in range(3):
            value = _extract_bits_from_array(msg, p, 8)
            p += 8
            result_str += str(hex(value)) + ", "
        result_str = result_str[:-2] + "]"
        return p, result_str

    def parse_one_time(msg, pos):
        result_str = "; OneTimeMode: ["
        p = pos
        num_intervals = _extract_bits_from_array(msg, p, 4)
        p += 4
        result_str += "NumIntervals: {}".format(num_intervals)
        result_str += "; Intervals: ["
        for i in range(num_intervals):
            result_str += "Interval {}: [".format(i + 1)
            if i == 0:
                start = _extract_bits_from_array(msg, p, 23)
                p += 23
            else:
                start = _extract_bits_from_array(msg, p, 10)
                p += 10
            result_str += "Start: {}, ".format(start)
            end = _extract_bits_from_array(msg, p, 10)
            p += 10
            result_str += "End {}]; ".format(end)
        result_str = result_str[:-2] + "]]"
        return p, result_str

    def parse_scheduled(msg, pos):
        result_str = "; ScheduledMode: ["
        p = pos
        mode = _extract_bits_from_array(msg, p, 1)
        p += 1
        result_str += "Mode: {} [".format(["Daily:", "Weekly:"][mode])
        if mode == 0:
            num_intervals = _extract_bits_from_array(msg, p, 4)
            p += 4
            result_str += "NumIntervals: {}".format(num_intervals)
            result_str += "; Intervals: ["
            for i in range(num_intervals):
                result_str += "Interval {}: [".format(i + 1)
                start = _extract_bits_from_array(msg, p, 7)
                p += 7
                result_str += "Start: {}, ".format(start)
                end = _extract_bits_from_array(msg, p, 7)
                p += 7
                result_str += "End {}]; ".format(end)
            result_str = result_str[:-2] + "]]]"
        else:
            for w in weekdays:
                result_str += w + " ["
                num_intervals = _extract_bits_from_array(msg, p, 2)
                p += 2
                result_str += "NumIntervals: {}".format(num_intervals)
                result_str += "; Intervals: ["
                for i in range(num_intervals):
                    result_str += "Interval {}: [".format(i + 1)
                    start = _extract_bits_from_array(msg, p, 7)
                    p += 7
                    result_str += "Start: {}, ".format(start)
                    end = _extract_bits_from_array(msg, p, 7)
                    p += 7
                    result_str += "End {}]; ".format(end)
                result_str = result_str[:-2] + "]]; "
            result_str = result_str[:-2] + "]"
        return p, result_str

    msg_base_parser = [
        ["Version", {"bits": 3}],
        [
            "SchedulingMode",
            {"bits": 2, "values": ["Disabled", "OneTime", "Scheduled"], "save": "sch_mode"},
        ],
        [
            "Sampling Action",
            {"bits": 1, "values": ["DisableSampling", "SkipSamples"], "save": "samp_action"},
        ],
        [
            "NumSkippedActions",
            {
                "bits": 8,
                "cond": lambda saves: saves["samp_action"] == "SkipSamples",
                "func": parse_skipped_samples,
            },
        ],
        ["UnconventionalActionCode", {"bits": 4, "values": action_codes, "save": "action_code"}],
        [
            "UnconventionalPayload",
            {
                "cond": lambda saves: saves["action_code"] in actions_with_payload,
                "func": parse_action_payload,
            },
        ],
        ["TimezoneCorrection", {"bits": 7, "signed": 1}],
        ["IntervalState", {"bits": 1}],
        [
            "OneTimePayload",
            {"cond": lambda saves: saves["sch_mode"] == "OneTime", "func": parse_one_time},
        ],
        [
            "ScheduledPayload",
            {"cond": lambda saves: saves["sch_mode"] == "Scheduled", "func": parse_scheduled},
        ],
    ]

    sampling_scheduler_cfg_str = ""
    saved_data = {}
    p = 0
    for key, info in msg_base_parser:
        if "cond" not in info:
            value = _extract_bits_from_array(msg, p, info["bits"])
            p += info["bits"]
            if "values" in info:
                value = info["values"][value]
            if "signed" in info:
                l_bits = info["bits"]
                if value > 2 ** (l_bits - 1) - 1:
                    value = -1 * (2 ** (l_bits)) + value
            sampling_scheduler_cfg_str += "; {}: {}".format(key, value)
            if "save" in info:
                saved_data[info["save"]] = value
        elif info["cond"](saved_data):
            p, result_str = info["func"](msg, p)
            sampling_scheduler_cfg_str += result_str

    return sampling_scheduler_cfg_str


def _inmsg_get_type_msg_str(msg_type, msg):
    if msg_type == 0:
        type_msg_str = "GetConfig " + _inmsg_get_config_str(msg)
    elif msg_type == 1:
        type_msg_str = "Get Health"
    elif msg_type == 2:
        type_msg_str = "Get Data "
    elif msg_type == 3:
        type_msg_str = "Recover Data" + _inmsg_recover_data_str(msg)
    elif msg_type == 4:
        type_msg_str = "Get Interval Data"
    elif msg_type == 5:
        type_msg_str = "Set Time " + _inmsg_set_time_str(msg)
    elif msg_type == 7:
        type_msg_str = "Set Node ID " + _inmsg_set_node_id_str(msg)
    elif msg_type == 8:
        type_msg_str = "Request Factory Reset " + _inmsg_factory_reset_str(msg)
    elif msg_type == 9:
        type_msg_str = "Request Reboot"
    elif msg_type == 10:
        type_msg_str = "Request LoRa Coverage Test " + _inmsg_lora_coverage_str(msg)
    elif msg_type == 15:
        type_msg_str = "Get Lora Session"
    elif msg_type == 21:
        type_msg_str = "Get Misc Test Commands Status" + _get_misc_cmd_status_str(msg)
    elif msg_type == 67:
        type_msg_str = "Get Node Info"  # Rest of the message is for backward compatibility
    elif msg_type == 128:
        type_msg_str = "Set VW Config" + _get_vw_config_str(msg)
    elif msg_type == 129:
        type_msg_str = "Set GSI Ch Config" + _get_gsi_ch_config_str(msg)
    elif msg_type == 130:
        type_msg_str = "Set SP Config" + _get_sp_config_str(msg)
    elif msg_type == 131:
        type_msg_str = "Set LoRa Addr Config" + _get_lora_addr_config_str(msg)
    elif msg_type == 132:
        type_msg_str = "Set LoRa General Config" + _get_lora_general_config_str(msg)
    elif msg_type == 133:
        type_msg_str = "Set LoRa Ch Grp0 Config" + _get_lora_ch_config_str(msg, 0)
    elif msg_type == 134:
        type_msg_str = "Set LoRa Ch Grp1 Config" + _get_lora_ch_config_str(msg, 1)
    elif msg_type == 142:
        type_msg_str = "Set LoRa Ch FCC Down Config" + _get_lora_ch_config_str(msg, 0)
    elif msg_type == 141:
        type_msg_str = "Set LoRa Key Config" + _inmsg_set_lora_keys_config_str(msg)
    elif msg_type == 143:
        type_msg_str = "Set " + _get_volt_sipi_config_str(msg)
    elif msg_type == 144:
        type_msg_str = "Set LoRa Slot Time Config" + _get_lora_slot_time_config_str(msg)
    elif msg_type == 145:
        type_msg_str = "Set Dig Ch Config" + _get_dig_ch_config_str(msg)
    elif msg_type == 146:
        type_msg_str = "Set Tilt Ch Config" + _get_tilt_ch_calib_str(msg)
    elif msg_type == 147:
        type_msg_str = "Set Pnode Ch Config" + _get_pnode_ch_config_str(msg)
    elif msg_type == 148:
        type_msg_str = "Set Lora Join Config" + _get_lora_join_config_str(msg)
    elif msg_type == 149:
        type_msg_str = "Set Supply Threshold" + _get_supply_threshold_str(msg)
    elif msg_type == 150:
        type_msg_str = "VW Magnitude Threshold" + _get_vw_magnitude_threshold_str(msg)
    elif msg_type == 151:
        type_msg_str = "Generic Modbus Instructions Config" + _get_gmm_instructions_cfg(msg)
    elif msg_type == 152:
        type_msg_str = "Set Tilt360 Ch Config" + _get_tilt360_ch_calib_str(msg)
    elif msg_type == 156:
        type_msg_str = "Set Tilt360A SP Config" + _get_t360a_sp_alert_config_str(msg)
    elif msg_type == 157:
        type_msg_str = "Get Sampling Scheduler Cfg" + _get_sampling_scheduler_cfg_str(msg)
    elif msg_type == 192:
        type_msg_str = (
            "Set SP and ST AggConfig" + _get_sampling_period_and_slot_time_agg_config_str(msg)
        )
    elif msg_type == 193:
        type_msg_str = (
            "Set Tilt360 Ch and Tilt360A Alert SP AggConfig"
            + _get_tilt360alert_ch_config_sp_alert_aggcfg_str(msg)
        )
    else:
        type_msg_str = "Unknown   "

    return type_msg_str


def inputmsg2string(msg):

    msg_str = ""

    try:
        unp_type = _struct.unpack("!B", msg[:1])

        msg_type = unp_type[0]

        type_msg_str = _inmsg_get_type_msg_str(msg_type, msg[1:])

        msg_str = type_msg_str

    except _struct.error:
        print("ERROR unpacking message")
        _logging.error("Parsing msg")
        msg_str = ""
        for i in msg:
            msg_str += "%02x " % (ord(i))
        _logging.debug(msg_str)

    return msg_str


def _format_gnss_data(json_data):

    # Helper function to find measurements for a given address
    def get_measurements_for_address(address):
        measurements = {"latitude": "", "longitude": "", "altitude": "", "numSamples": ""}
        for measurement in json_data.get("measurements", []):
            if measurement["address"] == address:
                for value in measurement["values"]:
                    if value["name"] in measurements:
                        measurements[value["name"]] = value["value"]
        return measurements

    # Extract measurements for each address
    measurements_1h = get_measurements_for_address("a:00:00:00")
    measurements_6h = get_measurements_for_address("a:00:01:00")
    measurements_24h = get_measurements_for_address("a:00:02:00")

    # Format the string
    result_str = (
        f"nodeModel: {json_data.get('nodeModel')}; nodeId: {json_data.get('nodeId')}; "
        f"readTimestamp: {json_data.get('datetime')}; "
        f"lat1H: {measurements_1h['latitude']}; lon1H: {measurements_1h['longitude']}; "
        f"alt1H: {measurements_1h['altitude']}; samples1H: {measurements_1h['numSamples']}; "
        f"lat6H: {measurements_6h['latitude']}; lon6H: {measurements_6h['longitude']}; "
        f"alt6H: {measurements_6h['altitude']}; samples6H: {measurements_6h['numSamples']}; "
        f"lat24H: {measurements_24h['latitude']}; lon24H: {measurements_24h['longitude']}; "
        f"alt24H: {measurements_24h['altitude']}; samples24H: {measurements_24h['numSamples']}"
    )

    return result_str


def _format_gnss_stats(json_data):

    # Create a dictionary for fast lookup of source types based on address
    address_to_type = {source["address"]: source["type"] for source in json_data["sources"]}

    # Initialize a list to hold the final output strings
    formatted_measurements = []

    # Group the name-value pairs under each source_type
    for measurement in json_data["measurements"]:
        address = measurement["address"]
        source_type = address_to_type.get(
            address, "UnknownType"
        )  # Find the type for the current address

        # Create a list of name-value pairs for the current measurement
        name_value_pairs = [f"{value['name']}: {value['value']}" for value in measurement["values"]]

        # Join the name-value pairs with '; ' and format as requested
        formatted_measurement = f"{source_type}: [{'; '.join(name_value_pairs)}]"
        formatted_measurements.append(formatted_measurement)

    # Join all formatted measurements into a single string if needed
    data_output = "; ".join(formatted_measurements)

    result_str = (
        f"nodeModel: {json_data.get('nodeModel')}; nodeId: {json_data.get('nodeId')}; "
        f"readTimestamp: {json_data.get('datetime')}; "
        f"{data_output}"
    )
    return result_str


def _get_sane_format(msg_type, json_data):
    if msg_type == "gnssDataV1":
        return _format_gnss_data(json_data)
    if msg_type == "gnssStatsV1":
        return _format_gnss_stats(json_data)
    return None


def _json2string(json_msg, msg_type=None):
    beautified_string = _get_sane_format(msg_type, json_msg)
    if beautified_string:
        return beautified_string
    else:
        for key, value in json_msg.items():
            if isinstance(value, bytes):
                # Decode bytes to string
                json_msg[key] = value.hex()
        json_string = _json.loads(_json.dumps(json_msg))
        return "; ".join([f"{el}: {json_string[el]}" for el in json_string])
