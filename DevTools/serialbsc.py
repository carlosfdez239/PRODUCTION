import binascii
import logging
import struct

import serial

"""
SerialRcvTask.
Reads messages from serial port. The messages are packetized using the BSC protocol:
  - A DLE STX sequence marks the beginning of the message.
  - A DLE ETX sequence marks the end of the message.
  - Any DLE in the data is doubled.

4 states are defined to control the reception of the messages:
  - STOPPED: nothing is being received. Next expected char DLE.
  - FIRST DLE: Starting DLE received, waiting for a STX.
  - IN MESSAGE: Receiving data characters. A DLE changes the state.
  - DLE IN MESSAGE: One DLE in the data has been received, waiting for the next char:
     - A ETX ends the message
     - A second DLE translates into one DLE char in the data and the state is changed
       back to IN MESSAGE.

Relation between the states:
                           _________
        ----------------->|         |-----------------
        |                 | STOPPED |                |
        |     ----------->|_________|<------------   |
     ETX|     |                   ^              |   |DLE
        |     |!ETX && !DLE       |        !STX  |   |
        |     |  (error)          |       (error)|   |
       _|_____|_                  |            __|___v__
      |         |                 ----------  |         |
      | MSG DLE |             (rcv message |  | 1st DLE |
      |_________|               too long)  |  |_________|
        ^     |                            |         |
        |     |                            |         |
        |     |DLE (Put DLE in rcv buffer) |         |
     DLE|     |            _________       |         |STX
        |     ----------->|         |-------         |
        |                 | IN MSG  |                |
        ------------------|_________|<----------------
                            ^     |
                            |     |!DLE (Put read char in rcv buffer)
                            -------
"""
SERIAL_RCV_STOPPED_STATE = 1
SERIAL_RCV_FIRST_DLE_STATE = 2
SERIAL_RCV_IN_MESSAGE_STATE = 3
SERIAL_RCV_IN_MESSAGE_DLE_STATE = 4

SERIAL_DLE = 16
SERIAL_STX = 2
SERIAL_ETX = 3


def _rcv_message_from_mote(ser):
    rcv_state = SERIAL_RCV_STOPPED_STATE
    packet_buffer = "".encode()
    data_read = ""
    ret_dict = {"MsgStatus": "Ok", "Data": ""}
    while True:
        data_read = ser.read()
        if (
            data_read == "" or len(data_read) == 0
        ):  # Let the function exit if nothing is responding fast enough
            logging.error("TimeoutError")
            ret_dict["MsgStatus"] = "ErrorTimeout"
            return ret_dict

        if rcv_state == SERIAL_RCV_STOPPED_STATE:  # Next expected char: DLE
            if SERIAL_DLE == ord(data_read):
                rcv_state = SERIAL_RCV_FIRST_DLE_STATE
            # else:
            #    print "SerialRcvTask: Unexpected char in state %u. Reset message" % rcv_state
        elif rcv_state == SERIAL_RCV_FIRST_DLE_STATE:  # Next expected char: STX
            if SERIAL_STX == ord(data_read):
                packet_buffer = "".encode()
                rcv_state = SERIAL_RCV_IN_MESSAGE_STATE
            else:
                # print "SerialRcvTask: Unexpected char in state %u. Reset message" % rcv_state
                rcv_state = SERIAL_RCV_STOPPED_STATE
        elif rcv_state == SERIAL_RCV_IN_MESSAGE_STATE:  # Next expected char: STX
            # - DLE if control sequence is present
            # - Data character otherwise
            if SERIAL_DLE == ord(data_read):
                rcv_state = SERIAL_RCV_IN_MESSAGE_DLE_STATE  # First DLE found, change state. */
            else:
                packet_buffer += data_read
        elif rcv_state == SERIAL_RCV_IN_MESSAGE_DLE_STATE:  # Next expected char:
            #  - ETX if end of message
            #  - DLE if DLE is present in the data
            if SERIAL_DLE == ord(data_read):
                # Second DLE found: DLE present in data
                rcv_state = SERIAL_RCV_IN_MESSAGE_STATE
                packet_buffer += data_read
            elif SERIAL_ETX == ord(data_read):
                # DLE ETX found, end of message
                rcv_state = SERIAL_RCV_STOPPED_STATE
                ret_dict["Data"] = packet_buffer
                return ret_dict  # packet_buffer
            else:
                # print "SerialRcvTask: Unexpected char in state %u. Reset message" % rcv_state
                rcv_state = SERIAL_RCV_STOPPED_STATE
        else:
            logging.error("SerialRcvTask")
            ret_dict["MsgStatus"] = "SerialRcvTask"
            return ret_dict  # packet_buffer


def open_serial(dev_tty, to=3600.0, baudrate=115200):
    try:
        ser = serial.serial_for_url(dev_tty, baudrate, timeout=to)
    except (Exception):
        logging.error("E2: Opening serial port")
        raise NameError("Could not open serial port")
    return ser


def close_serial(ser):
    ser.close()


def send_message_to_mote(ser, msg):
    header = "1002"
    end = "1003"

    msg_scapped = ""
    for i in range(0, len(msg) - 1, 2):
        curr_byte = msg[i : i + 2]
        if curr_byte == "10":
            msg_scapped += "1010"
        else:
            msg_scapped += curr_byte

    msg = binascii.unhexlify("{}{}{}".format(header, msg_scapped, end))
    ser.write(msg)


def rcv_message_from_mote(ser):
    binary_dic = _rcv_message_from_mote(ser)
    msg_dict = {"MsgStatus": "Ok"}
    if binary_dic["MsgStatus"] != "Ok":
        msg_dict["MsgStatus"] = binary_dic["MsgStatus"]
    else:
        try:
            msg = binary_dic["Data"]
            msg2 = msg.hex()
            msg_dict["Data"] = binascii.unhexlify("{}".format(msg2))
            return msg_dict

        except struct.error:
            logging.error("Error parsing msg")
            raise NameError("Could not parse msg")

    return msg_dict
