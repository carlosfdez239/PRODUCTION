import copy as _copy

from ls_message_parsing.ls_message_parsing import encode_msg as _encode_msg


def _calculatecrc16(payload, payload_length):
    crc_16_ccitt_init = 0x0000
    crc_16_ccitt_poly = 0x1021
    crc = crc_16_ccitt_init
    for i in range(payload_length):
        crc = crc ^ payload[i] << 8
        for j in range(8):
            if (crc & 0x8000) != 0:
                crc = (crc << 1) ^ crc_16_ccitt_poly
            else:
                crc = crc << 1
    crc = 0x0000FFFF & crc
    return crc


def _set_slot_time(slot_time):
    return f"90{slot_time:04X}"


def _set_pr_code(password, version, product_code, serial_number):
    return f"13{password:08X}{version:02X}{product_code:02X}{serial_number:08X}"


def _set_nodeid(node_id, password):
    return f"14{password:08X}{node_id:010X}"


def _bool_to_bit(s):
    if s in ("True", "TRUE", "true", "1", True):
        return 1
    elif s in ("False", "FALSE", "false", "0", False):
        return 0
    else:
        return None


def _set_lora_general_config(
    mac_version,
    use500khzch,
    radioenabled,
    etsienabled,
    adrenabled,
    sf,
    txpower,
    userx2,
    rx2sf,
    rx2freq,
):
    msgversion = 0  # It is possible that in the future some other version of the message is needed
    use500khzch = _bool_to_bit(use500khzch) * 8
    radioenabled = _bool_to_bit(radioenabled) * 4
    etsienabled = _bool_to_bit(etsienabled) * 2
    adrenabled = _bool_to_bit(adrenabled)
    byte_bool1 = use500khzch + radioenabled + etsienabled + adrenabled
    userx2 = _bool_to_bit(userx2)
    # 3bits reserved
    bitreserved1 = 0  # RESERVED _bool_to_bit(reserved1)*8
    bitreserved2 = 0  # RESERVED _bool_to_bit(reserved2)*4
    bitreserved3 = 0  # RESERVED _bool_to_bit(reserved3)*2
    byte_bool2 = userx2 + bitreserved1 + bitreserved2 + bitreserved3
    st_dep = 0  # Deprecated from v2.15 onwards
    return (
        f"84{msgversion:01X}{mac_version:01X}{byte_bool1:01X}{sf:01X}{txpower:02X}"
        f"{byte_bool2:01X}{rx2sf:01X}{rx2freq:08X}{st_dep:04X}"
    )


def _set_hwversion(version, password, hw_brd1_major, hw_brd1_minor, hw_brd2_major, hw_brd2_minor):
    return f"0d{version:02X}{password:08X}{hw_brd1_major:02X}{hw_brd1_minor:02X}{hw_brd2_major:02X}{hw_brd2_minor:02X}"


def _set_lora_keys_config(appkey, netkey, networkid):
    address = f"{networkid:08X}"
    payload = str(appkey) + str(netkey) + str(address)
    buffer_aux = [int(payload[i * 2 : i * 2 + 2], base=16) for i in range(int(len(payload) / 2))]
    bufflength = len(buffer_aux)
    crc = _calculatecrc16(bytearray(buffer_aux), bufflength)
    return f"8D{appkey}{netkey}{address}{crc:04X}"


def _get_recover_all_data(ls_am_type_data, start_time, end_time):
    """
    method to construct the message used to recover all data:
        AM_TYPE         - 1 byte
        LSAMTYPE_DATA   - 1 byte
        Start Time      - 4 bytes
        End Time        - 4 bytes
    :param ls_am_type_data: the type of data to recover input
    :param start_time: Start interval time of data
    :param end_time: End interval time of data
    :return: constructed message
    """
    am_type = 3
    gen_str = (
        f"{int(am_type):02X}{int(ls_am_type_data):02X}{int(start_time):08X}{int(end_time):08X}"
    )
    return gen_str


def _aggregated_config(sampling_period, slot_time):
    return f"C0{int(sampling_period):06X}{int(slot_time):04X}"


def _time_correction(sign, correction, token):
    if sign == "1" or sign == "0" or sign == 1 or sign == 0:
        return f"0C{int(sign):02X}{int(correction):08X}{int(token):08X}"
    else:
        raise ValueError("Sign must be 1 if negative or 0 if positive!")


def _factory_reset(password):
    return f"08{password:08X}"


def _coverage_test(token):
    """
    method that encodes the coverage test message
    :param token: token used
    :type token: str
    :return: encoded message
    :rtype: str
    """
    am_type = 10
    return f"{am_type:02x}{token}"


def _digsisgeolegchcfg(
    am_type,
    type_of_sensors,
    config_version,
    num_channels,
    address_delay,
    warning_delay,
    addr_channels,
):
    """
    method that encodes the Geosense’s Inclinometers channel config test message
        AM_TYPE         - 1 byte
        type_of_sensors - 1 byte
        byte1           - Reserved(4bits)
                          +config_version(4bits)
        byte2
                          +Reserved(2bits)
                          +num_channels(6bit) [0...30]
        address_delay  - 1 byte
        warning_delay  - 1 byte
        addr_ch_n      - 1 byte/channel
    :param am_type: the type of data to recover input
    :type am_type: int
    :param type_of_sensors: the type of sensor connected to the mote
    :type type_of_sensors: int
    :param config_version: the version of the configuration
    :type config_version: int
    :param num_channels: the number of channel used
    :type num_channels: int
    :param address_delay: the address part of the communication window configuration
    :type address_delay: int
    :param warning_delay: the warmup part of the communication window configuration
    :type warning_delay: int
    :param addr_channels: list of the channels that came in int
    :type addr_channels: list
    :return: constructed message
    :rtype: str
    """
    reserved = 0
    byte1 = "{:04b}".format(reserved) + "{:04b}".format(config_version)
    byte2 = "{:02b}".format(reserved) + "{:06b}".format(num_channels)
    addr_ch_n = ""
    for i in addr_channels:
        addr_ch_n = addr_ch_n + f"{i:02X}"
    return (
        f"{am_type:02X}{type_of_sensors:02X}{int(byte1,2):02X}{int(byte2,2):02X}{address_delay:02X}"
        f"{warning_delay:02X}{addr_ch_n}"
    )


def _format_dec_list_to_str_hex(id_channels_list):
    """
    method prepare a concatenated string from a list of decimal numbers into a string of hexadecimal values.
    It also fills with a trailing 0 to correctly convert the message to hexadecimal.
    :param id_channels_list: the IDs of channel used
    :type id_channels_list: int
    :return: constructed message(string)
    :rtype: string
    """
    ids = _copy.deepcopy(id_channels_list)
    id_ch_bit = "{:012b}".format(ids[0])
    ids.pop(0)
    for i in ids:
        id_ch_bit = id_ch_bit + "{:012b}".format(i)
    if len(ids) % 8 != 0:
        rest = len(id_ch_bit) % 8
        id_ch_bit = id_ch_bit + "{:01b}".format(0) * rest
    code = ""
    for i in range(0, int(len(id_ch_bit) / 8)):
        code = code + "{:02X}".format(int(id_ch_bit[i * 8 : 8 + 8 * i], 2))
    return code


def _diggeoflexchcfg(
    am_type,
    type_of_sensors,
    config_version,
    num_sensors,
    channels_bitmask,
    data_wait_time,
    id_sensors,
):
    """
    method that encodes the Geosense’s Inclinometers channel config test message
        AM_TYPE         - 1 byte
        type_of_sensors   - 1 byte
        byte1           - Reserved(4bits)
                          +config_version(4bits)
        byte2
                          +Reserved(2bits)
                          +num_sensors(6bit) [0...50]
        channels_bitmask - 1 byte
        data_wait_time   - 2 bytes   [0...65535]
        IdSensor N       - 12 bits/Sensor   [0...40695]
        Padding          - X bits depending on the Nº of sensors
    :param am_type: the type of data to recover input
    :type am_type: int
    :param type_of_sensors: the type of sensor connected to the mote
    :type type_of_sensors: int
    :param config_version: the version of the configuration
    :type config_version: int
    :param num_sensors: the number of channel used
    :type num_sensors: int
    :param channels_bitmask: the Bitmask with the number of channels (axis)
    :type channels_bitmask: int
    :param data_wait_time: the time needed for getting one data in ms
    :type data_wait_time: int
    :param id_sensors: list of the channels that came in int
    :type id_sensors: list
    :return: constructed message
    :rtype: str
    """
    reserved = 0
    byte1 = "{:04b}".format(reserved) + "{:04b}".format(config_version)
    byte2 = "{:02b}".format(reserved) + "{:06b}".format(num_sensors)
    snsr_ch_n = _format_dec_list_to_str_hex(id_sensors)
    return (
        f"{am_type:02X}{type_of_sensors:02X}{int(byte1,2):02X}{int(byte2,2):02X}"
        f"{channels_bitmask:02X}{data_wait_time:04X}" + snsr_ch_n
    )


# Usage
"""
import ls_json2msg
import serialbsc
msg_json = { 'type' : ls_json2msg.msg_types['req_health'] }
mote_msg = ls_json2msg.json2msg(msg_json)
serialbsc.send_message_to_mote(mote_msg)
"""
msg_types = {
    "coverage_test": "icoverage_test",
    "factory_reset": "ifactory_reset",
    "get_PrCodeSn": "iget_PrCodeSn",
    "get_data": "iget_data",
    "get_intervalData": "iget_intervalData",
    "get_loraAddr": "iget_loraAddr",
    "get_loraChannelConfig": "iget_loraChannelConfig",
    "get_loraGeneralConfig": "iget_loraGeneralConfig",
    "get_loraJoinConfig": "iget_loraJoinConfig",
    "get_loraKeysConfig": "iget_loraKeysConfig",
    "get_loraPassword": "iget_loraPassword",
    "get_nodeExtendedInfo": "iget_nodeExtendedInfo",
    "get_nodeInfo": "iget_nodeInfo",
    "get_samplingPeriodConfig": "iget_samplingPeriodConfig",
    "get_samplingPeriodTilt360AlertConfig": "iget_samplingPeriodTilt360AlertConfig",
    "get_slotTime": "iget_slotTime",
    "get_tiltConfigutarionChannelConfig": "iget_tiltConfigutarionChannelConfig",
    "get_lastil90ChCfg": "iget_lastil90ChCfg",
    "get_vw5ChCfg": "iget_vw5ChCfg",
    "get_vw1ChCfg": "iget_vw1ChCfg",
    "get_til90ChCfg": "iget_til90ChCfg",
    "get_pnode_ConfigutarionChannelConfig": "iget_pnode_ConfigutarionChannelConfig",
    "get_voltChannelConfig": "iget_voltChannelConfig",
    "get_digital": "iget_digital",
    "reboot": "ireboot",
    "recover_allData": "irecover_allData",
    "req_health": "ireq_health",
    "set_loraAddr": "iset_loraAddr",
    "set_loraChGrp0Config_ce_euro": "iset_loraChGrp0Config_ce_euro",
    "set_loraGeneralConfig": "iset_loraGeneralConfig",
    "set_loraJoinConfig_framemode_1": "iset_loraJoinConfig_framemode_1",
    "set_loraKeysConfig": "iset_loraKeysConfig",
    "set_lora_addrChannelConfig_gw_default_defaultTestConfig": "iset_lora_addrChannelConfig_gw_default"
    "_defaultTestConfig",
    "set_lora_channel_config_lora_wan_868_freqs": "iset_lora_channel_config_lora_wan_868_freqs",
    "set_lora_wan_channel_config_923a_group_0_freqs": "iset_lora_wan_channel_config_923a_group_0_freqs",
    "set_lora_wan_channel_config_923a_group_1_freqs": "iset_lora_wan_channel_config_923a_group_1_freqs",
    "set_lora_wan_channel_config_923a_group_2_freqs": "iset_lora_wan_channel_config_923a_group_2_freqs",
    "set_lora_wan_channel_config_923a_group_3_freqs": "iset_lora_wan_channel_config_923a_group_3_freqs",
    "set_lora_wan_channel_config_923a_group_4_freqs": "iset_lora_wan_channel_config_923a_group_4_freqs",
    "set_lora_wan_channel_config_923a_group_5_freqs": "iset_lora_wan_channel_config_923a_group_5_freqs",
    "set_lora_wan_channel_config_923a_group_6_freqs": "iset_lora_wan_channel_config_923a_group_6_freqs",
    "set_lora_wan_channel_config_923a_group_7_freqs": "iset_lora_wan_channel_config_923a_group_7_freqs",
    "set_lora_wan_channel_config_922s": "iset_lora_wan_channel_config_922s",
    "set_lora_channelConfig_866I": "iset_lora_channelConfig_866I",
    "set_lora_channelConfig_923a_group_0_freqs": "iset_lora_channelConfig_923a_group_0_freqs",
    "set_lora_channelConfig_923a_group_1_freqs": "iset_lora_channelConfig_923a_group_1_freqs",
    "set_lora_channelConfig_916I": "iset_lora_channelConfig_916I",
    "set_lora_channelConfig_922B_group_0_freqs": "iset_lora_channelConfig_922B_group_0_freqs",
    "set_lora_channelConfig_922B_group_1_freqs": "iset_lora_channelConfig_922B_group_1_freqs",
    "set_lora_channelConfig_922B_group_2_freqs": "iset_lora_channelConfig_922B_group_2_freqs",
    "set_lora_channelConfig_922B_group_3_freqs": "iset_lora_channelConfig_922B_group_3_freqs",
    "set_lora_channelConfig_922B_group_4_freqs": "iset_lora_channelConfig_922B_group_4_freqs",
    "set_lora_channelConfig_922B_group_5_freqs": "iset_lora_channelConfig_922B_group_5_freqs",
    "set_lora_channelConfig_922B_group_6_freqs": "iset_lora_channelConfig_922B_group_6_freqs",
    "set_lora_channelConfig_922B_group_7_freqs": "iset_lora_channelConfig_922B_group_7_freqs",
    "set_lora_channelConfig_922K": "iset_lora_channelConfig_922K",
    "set_lora_channelConfig_922S": "iset_lora_channelConfig_922S",
    "set_lora_channelConfig_923M_group_0_freqs": "iset_lora_channelConfig_923M_group_0_freqs",
    "set_lora_channelConfig_923M_group_1_freqs": "iset_lora_channelConfig_923M_group_1_freqs",
    "set_lora_channelConfig_923P": "iset_lora_channelConfig_923P",
    "set_lora_channelConfig_923T_group_0_freqs": "iset_lora_channelConfig_923T_group_0_freqs",
    "set_lora_channelConfig_923T_group_1_freqs": "iset_lora_channelConfig_923T_group_1_freqs",
    "set_lora_channelConfig_926C": "iset_lora_channelConfig_926C",
    "set_lora_channelConfig_915_group_0_freqs": "iset_lora_channelConfig_915_group_0_freqs",
    "set_lora_channelConfig_915_group_1_freqs": "iset_lora_channelConfig_915_group_1_freqs",
    "set_lora_channelConfig_915_group_2_freqs": "iset_lora_channelConfig_915_group_2_freqs",
    "set_lora_channelConfig_915_group_3_freqs": "iset_lora_channelConfig_915_group_3_freqs",
    "set_lora_channelConfig_915_group_4_freqs": "iset_lora_channelConfig_915_group_4_freqs",
    "set_lora_channelConfig_915_group_5_freqs": "iset_lora_channelConfig_915_group_5_freqs",
    "set_lora_channelConfig_915_group_6_freqs": "iset_lora_channelConfig_915_group_6_freqs",
    "set_lora_channelConfig_915_group_7_freqs": "iset_lora_channelConfig_915_group_7_freqs",
    "set_nodeHWversion": "iset_nodeHWversion",
    "set_nodeid": "iset_nodeId",
    "set_productCode": "iset_productCode",
    "set_samplingPeriodConfig": "iset_samplingPeriodConfig",
    "set_samplingPeriodTilt360AlertConfig": "iset_samplingPeriodTilt360AlertConfig",
    "set_slotTime": "iset_slotTime",
    "set_tiltConfigutarionChannelConfig_default": "iset_tiltConfigutarionChannelConfig_default",
    "set_lastil90ChCfg": "iset_lastil90ChCfg",
    "set_vw5ChCfg": "iset_vw5ChCfg",
    "set_vw1ChCfg": "iset_vw1ChCfg",
    "set_til90ChCfg": "iset_til90ChCfg",
    "set_voltChannelConfig_4Channels": "iset_voltChannelConfig_4Channels",
    "set_time": "iset_time",
    "set_timeCorrection": "iset_timeCorrection",
    "set_aggregatedConfig": "iset_aggregatedConfig",
    "set_digsisgeolegchcfg": "iset_digsisgeolegchcfg",
    "set_diggeoflexchcfg": "iset_diggeoflexchcfg",
}
_json_type_to_mote_msg = {
    "icoverage_test": _coverage_test,
    "ifactory_reset": _factory_reset,
    "iget_PrCodeSn": "43690000",
    "iget_data": "02",
    "iget_intervalData": "04",
    "iget_loraAddr": "0083",
    "iget_loraChannelConfig": "0085",
    "iget_loraGeneralConfig": "0084",
    "iget_loraJoinConfig": "0094",
    "iget_loraKeysConfig": "008D",
    "iget_loraPassword": "008D",
    "iget_nodeExtendedInfo": "0E",
    "iget_nodeInfo": "43690000",
    "iget_samplingPeriodConfig": "0082",
    "iget_samplingPeriodTilt360AlertConfig": "009C",
    "iget_slotTime": "0090",
    "iget_tiltConfigutarionChannelConfig": "009B",
    "iget_lastil90ChCfg": "0099",
    "iget_vw5ChCfg": "0080",
    "iget_vw1ChCfg": "0080",
    "iget_til90ChCfg": "009A",
    "iget_pnode_ConfigutarionChannelConfig": "0093",
    "iget_voltChannelConfig": "008f",
    "iget_digital": "0091",
    "iget_dynCfg": "009e",
    "ireboot": "09",
    "irecover_allData": _get_recover_all_data,
    "ireq_health": "01",
    "iset_loraAddr": (lambda loraAddr: f"83{loraAddr:08X}"),
    "iset_loraChGrp0Config_ce_euro": "8500F036D6160036E5584036F49A803703DCC000000000000000000000000000000000",
    "iset_loraGeneralConfig": _set_lora_general_config,
    "iset_loraJoinConfig_framemode_1": "940000112233445566778899AABBCCDDEEFF2710020E0140",
    "iset_loraKeysConfig": _set_lora_keys_config,
    "iset_lora_addrChannelConfig_gw_default_defaultTestConfig": "8500FC33BE27A033C134E033C4422033C9995033CCA69033D3E608"
    "0000000000000000",
    "iset_lora_channel_config_lora_wan_868_freqs": "8500FF33BE27A033C134E033C4422033AEE56033B1F2A033B4FFE033B80D2033BB1"
    "A60",
    "iset_lora_wan_channel_config_923a_group_0_freqs": "8500FF368CD800368FE5403692F2803695FFC036990D00369C1A40369F27803"
    "6A234C0",
    "iset_lora_wan_channel_config_923a_group_1_freqs": "8500FF36A5420036A84F4036AB5C8036AE69C036B1770036B4844036B791803"
    "6BA9EC0",
    "iset_lora_wan_channel_config_923a_group_2_freqs": "8500FF36BDAC0036C0B94036C3C68036C6D3C036C9E10036CCEE4036CFFB803"
    "6D308C0",
    "iset_lora_wan_channel_config_923a_group_3_freqs": "8500FF36D6160036D9234036DC308036DF3DC036E24B0036E5584036E865803"
    "6EB72C0",
    "iset_lora_wan_channel_config_923a_group_4_freqs": "8500FF36EE800036F18D4036F49A8036F7A7C036FAB50036FDC2403700CF803"
    "703DCC0",
    "iset_lora_wan_channel_config_923a_group_5_freqs": "8500FF3706EA003709F740370D0480371011C037131F0037162C40371939803"
    "71C46C0",
    "iset_lora_wan_channel_config_923a_group_6_freqs": "8500FF371F54003722614037256E8037287BC0372B8900372E96403731A3803"
    "734B0C0",
    "iset_lora_wan_channel_config_923a_group_7_freqs": "8500FF3737BE00373ACB40373DD8803740E5C03743F30037470040374A0D803"
    "74D1AC0",
    "iset_lora_wan_channel_config_922s": "8500FF36F49A8036F7A7C036FAB50036FDC2403700CF803703DCC03706EA003709F740",
    "iset_lora_channelConfig_866I": "8500FF33936E2033967B60339988A0339C95E0339FA32033A2B06033A5BDA033A8CAE0",
    "iset_lora_channelConfig_923a_group_0_freqs": "8500FF36AB5C8036AE69C036B1770036B4844036B7918036BA9EC036BDAC0036C0B9"
    "40",
    "iset_lora_channelConfig_923a_group_1_freqs": "8500FF36D6160036D9234036DC308036DF3DC036E24B0036E5584036E8658036EB72"
    "C0",
    "iset_lora_channelConfig_916I": "8500FF368E5EA036916BE03694792036978660369A93A0369DA0E036A0AE2036A3BB60",
    "iset_lora_channelConfig_922B_group_0_freqs": "8500FF368B5160368E5EA036916BE03694792036978660369A93A0369DA0E036A0AE"
    "20",
    "iset_lora_channelConfig_922B_group_1_freqs": "8500FF36A3BB6036A6C8A036A9D5E036ACE32036AFF06036B2FDA036B60AE036B918"
    "20",
    "iset_lora_channelConfig_922B_group_2_freqs": "8500FF36BC256036BF32A036C23FE036C54D2036C85A6036CB67A036CE74E036D182"
    "20",
    "iset_lora_channelConfig_922B_group_3_freqs": "8500FF36D48F6036D79CA036DAA9E036DDB72036E0C46036E3D1A036E6DEE036E9EC"
    "20",
    "iset_lora_channelConfig_922B_group_4_freqs": "8500FF36ECF96036F006A036F313E036F6212036F92E6036FC3BA036FF48E0370256"
    "20",
    "iset_lora_channelConfig_922B_group_5_freqs": "8500FF37056360370870A0370B7DE0370E8B20371198603714A5A03717B2E0371AC0"
    "20",
    "iset_lora_channelConfig_922B_group_6_freqs": "8500FF371DCD603720DAA03723E7E03726F520372A0260372D0FA037301CE037332A"
    "20",
    "iset_lora_channelConfig_922B_group_7_freqs": "8500FF37363760373944A0373C51E0373F5F2037426C60374579A0374886E0374B94"
    "20",
    "iset_lora_channelConfig_922K": "8500FE36F6212036F92E6036FC3BA036FF48E03702562037056360370870A000000000",
    "iset_lora_channelConfig_922S": "8500E736E3D1A036E8658036ECF96000000000000000003700CF80370563603709F740",
    "iset_lora_channelConfig_923M_group_0_freqs": "8500FF36F6212036F92E6036FC3BA036FF48E03702562036C85A6036CB67A036CE74"
    "E0",
    "iset_lora_channelConfig_923M_group_1_freqs": "8500FF36D1822036D48F6036D79CA036DAA9E036DDB72036E0C46036E3D1A036E6DE"
    "E0",
    "iset_lora_channelConfig_923P": "8500FF36EB72C036EE800036F18D4036F49A8036F7A7C036FAB50036FDC2403700CF80",
    "iset_lora_channelConfig_923T_group_0_freqs": "8500FF36F313E036F6212036F92E6036FC3BA036FF48E03702562037056360370870"
    "A0",
    "iset_lora_channelConfig_923T_group_1_freqs": "8500FF370B7DE0370E8B20371198603714A5A03717B2E0371AC020371DCD603720DA"
    "A0",
    "iset_lora_channelConfig_926C": "85007F0000000037287BC0372B8900372E96403731A3803734B0C03737BE00373ACB40",
    "iset_lora_channelConfig_915_group_0_freqs": "8500FF35C8016035CB0EA035CE1BE035D1292035D4366035D743A035DA50E035DD5E2"
    "0",
    "iset_lora_channelConfig_915_group_1_freqs": "8500FF35E06B6035E378A035E685E035E9932035ECA06035EFADA035F2BAE035F5C82"
    "0",
    "iset_lora_channelConfig_915_group_2_freqs": "8500FF35F8D56035FBE2A035FEEFE03601FD2036050A60360817A0360B24E0360E322"
    "0",
    "iset_lora_channelConfig_915_group_3_freqs": "8500FF36113F6036144CA0361759E0361A6720361D7460362081A036238EE036269C2"
    "0",
    "iset_lora_channelConfig_915_group_4_freqs": "8500FF3629A960362CB6A0362FC3E03632D1203635DE603638EBA0363BF8E0363F062"
    "0",
    "iset_lora_channelConfig_915_group_5_freqs": "8500FF36421360364520A036482DE0364B3B20364E4860365155A0365462E03657702"
    "0",
    "iset_lora_channelConfig_915_group_6_freqs": "8500FF365A7D60365D8AA0366097E03663A5203666B2603669BFA0366CCCE0366FDA2"
    "0",
    "iset_lora_channelConfig_915_group_7_freqs": "8500FF3672E7603675F4A0367901E0367C0F20367F1C60368229A0368536E03688442"
    "0",
    "iset_nodeHWversion": _set_hwversion,
    "iset_nodeId": _set_nodeid,
    "iset_productCode": _set_pr_code,
    "iset_samplingPeriodConfig": (lambda samplingperiod: f"82{samplingperiod:06X}"),
    "iset_samplingPeriodTilt360AlertConfig": (
        lambda samplingperiodOfAlertState: f"9C{samplingperiodOfAlertState:06X}"
    ),
    "iset_slotTime": _set_slot_time,
    "iset_tiltConfigutarionChannelConfig_default": "9B0E051947C1807D173601F40000",
    "iset_lastil90ChCfg": "991F",
    "iset_vw5ChCfg": "8000070801020202020205780DAC0032",
    "iset_vw1ChCfg": "8000070801020202020205780DAC0032",
    "iset_til90ChCfg": "9A07",
    "iset_voltChannelConfig_4Channels": "8F0F03000000030000000300000003000000",
    "iset_time": (lambda targetTime: f"05{targetTime:08X}"),
    "iset_timeCorrection": _time_correction,
    "iset_aggregatedConfig": _aggregated_config,
    "iset_diggeoflexchcfg": _diggeoflexchcfg,
    "iset_digsisgeolegchcfg": _digsisgeolegchcfg,
}


def _mote_encode_messages(in_msg):
    """
    method used to encode the mote messages using the ls_message_parsing
    :param in_msg: data needed for the message encoding
    :type in_msg: dict
    :return: the method shall return the encoded message
    :rtype: str
    """
    in_msg = _copy.deepcopy(in_msg)
    try:
        encoded_response = _encode_msg(msg=in_msg).get_encoded_message_string().hex()
    except Exception as e:
        raise e
    return encoded_response


def json2msg(json_msg):
    """
    method used to encode the mote messages.
    The flow is:
         1. first it tries to use the ls_message_parsing in order to encode the mote messages;
         2. then if first method fails, use the internal implementation from this project.
    :param json_msg: the message data
    :type json_msg: dict
    :return: the method shall return the encoded message
    :rtype: str
    """
    mote_msg = None
    try:  # use the ls_message_parsing lib to encode the messages
        mote_msg = _mote_encode_messages(json_msg)
    except Exception:
        # robot.api.logger.info(
        #    "The message cannot be encoded using ls_message_parsing library: \t{msg}".format(
        #        msg=json_msg), html=True, also_console=True)
        # TODO When this lib is integrated with QA tools, decide if we want to log the warning and how to do so.
        pass
    if mote_msg is None:  # use the internal implementation to encode the messages
        internal_type = json_msg["type"]
        if not callable(_json_type_to_mote_msg[internal_type]):
            mote_msg = _json_type_to_mote_msg[internal_type]
        else:
            in_msg = dict(json_msg)
            del in_msg["type"]
            mote_msg = _json_type_to_mote_msg[internal_type](**in_msg)
    return mote_msg
