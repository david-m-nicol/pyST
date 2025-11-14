#!/usr/bin/env python3
"""Pymodbus asynchronous Server with interface to input-writing digital twin 
"""
import logging
import sys
import pdb
import mbstruct
import mbaux
import struct
import socket
import threading
import time

from pymodbus.datastore import (
    ModbusSequentialDataBlock,
)

# Modbus data block table variables

coilblock = None     
datablock = None     
inputRegblock = None
holdingRegblock = None

readDiscreteInputs   = 0x02
writeDiscreteInputs  = 0x62

readCoils  = 0x01
writeCoil  = 0x05
writeDiscreteInput = 0x65
writeCoils = 0x0F

readInputRegisters   = 0x04
writeInputRegisters  = 0x64

readHoldingRegisters  = 0x03
writeHoldingRegister  = 0x06
writeInputRegister    = 0x66
writeHoldingRegisters = 0x10

maskWriteRegister = 0x16
readWriteRegisters = 0x17

client_port = None
server_host = '127.0.0.1'
srvr_sock = None

tablesize = 100
transactionID = 1

# given the data table, an address in that table, and a number of elements,
# acquire those values from the data table and return them, doing a conversion
# for tables holding booleans
#
def getTableValues(table, adrs, size):
    try:
        values = table.getValues(adrs, size)
        trns_values = []
        # is the table of interest representing boolean variables?
        if table==coilblock or table==datablock:
            # yes, so create explicit conversions
            for v in values:
                if isinstance(v,int):
                    vt = True if v%2 > 0 else False
                    trns_values.append(vt)
        else:
            trns_values = values
        return True, trns_values

    except:
        return False, []

# given the data table, an address in that table, and a list of values,
# write those values to the data table, doing a conversion
# for tables holding booleans
#
def setTableValues(table, adrs, values):
    try:
        trns_values = []
        # does this table manage Booleans?
        if table == coilblock or table==datablock:
            # yes, so do a conversion to integers 
            for v in values:
                if isinstance(v,bool):
                    vt = 1 if v else 0
                    trns_values.append(vt) 
        else:
            trns_values = values

        table.setValues(adrs, trns_values)
        return True
    except:
        return False




unsupportedFuncs = (0x7, 0x8, 0xB, 0xC, 0x11, 0x14, 0x15, 0x18, 0x2B)


def srvr_thread_function(sock, extended=False):
    # look for a connection and when found spin off a thread to deal with it 
    sock.listen()
    while True:
        conn, addr = sock.accept()

        # spin off a thread to deal with this connection
        req_thread = threading.Thread(target=handle_request, args=(conn, extended))
        req_thread.start()
 
# handle requests is called to establish a session with a client.
# within the session individual modbus messages are received, each one responded to.
# the reader and writer arguments are the read and writeback connections to the client
#
def handle_request(conn, extended):
    with conn:
        while True:
            # loop where a message from the client is waited for.  The underlaying asyncio system
            # will flip attention to the pymodbus server loop, so this is not blocking in the sense
            # that waiting for the client message shuts out ability of other clients to interact
            # with the pymodbus server
            #
            data = conn.recv(512)   # modbus messages are always smaller than 512 bytes
            if not data:
                print(f"Client disconnected.")
                break
            # check the validity of the message
            #print(f"received {data}")
            valid, excpCode = mbaux.valid_modbus_msg(data, True, True, extended)

            # ignore an invalid message with a null exception code
            if not valid and excpCode==0:
                print("warning: received ill-formed modbus message [{data}]")
                continue
            elif not valid:
                # report an errorenous message, including the exception code
                pdu = struct.pack('>BB', 0x80+fc, excpCode)

            else:
                # Valid message. Determine the function code
                (transID, protID, msgLen, unitID) = struct.unpack('>HHHB', data[:7])
                fc = data[7]

                # peel off the PDU part of the message
                pdu_in = data[8:]

                # response depends on the function code
                if fc in (readCoils, readDiscreteInputs):
                    (adrs, numBits) = struct.unpack('>HH', pdu_in[:4])

                    if tablesize < adrs+numBits+1:
                        # err = True 
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        # get the bit values
                        if fc==readCoils:
                            OK, bits = getTableValues(coilblock, adrs, numBits)
                        else:
                            OK, bits = getTableValues(datablock, adrs, numBits)
                        if not OK:
                            pdu = struct.pack('>BB', 0x80+fc, 2)
                        else:
                            # if the number of bits returned is empty signal an error

                            # turn list of bools into a list of bit masks
                            bitBytes = mbstruct.make_bitmask_list(bits)

                            # build up response pdu : number of bytes in sequence of bitmasks, 
                            # then sequence of bitmasks 
                            pdu = struct.pack('>BB', fc, len(bitBytes))
                            for bbyte in bitBytes:
                                pdu = pdu + struct.pack('>B', bbyte)

                elif fc in (writeCoils, writeDiscreteInputs):
                    (adrs, numBits, bitVec) = mbstruct.unpack_bits_pdu(pdu_in)  
                    if tablesize < adrs+numBits+1:
                        # err = True 
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        if fc==writeCoils:
                            OK = setTableValues(coilblock, adrs, bitVec)
                        else:
                            OK = setTableValues(datablock, adrs, bitVec)

                        if not OK:
                            pdu = struct.pack('>BB', 0x80+fc, 4)
                        else:
                            pdu = struct.pack('>BHH', fc, adrs, numBits)

                elif fc in (writeCoil, writeDiscreteInput):
                    (adrs, value) = struct.unpack('>HH', pdu_in[:4])
                    if tablesize <= adrs:
                        # err = True
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        bit = True if value != 0 else False
                        if fc==writeCoil:
                            setTableValues(coilblock, adrs, [bit])
                        else:
                            setTableValues(datablock, adrs, [bit])

                        pdu = struct.pack('>BHH', fc, adrs, value)

                elif fc in (readInputRegisters, readHoldingRegisters):
                    (adrs, numValues) = mbstruct.unpack_read_registers_pdu(pdu_in[:4])
                    if tablesize < adrs+numValues+1:
                        # err = True
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        # get the vectors of register values from the data blocks
                        if fc==readInputRegisters:
                            OK, values = getTableValues(inputRegblock, adrs, numValues)
                        else:
                            OK, values = getTableValues(holdingRegblock, adrs, numValues)
                        if not OK:
                            pdu = struct.pack('>BB', 0x80+fc, 2)
                        else:
                            valuesBytes = mbstruct.make_values_list(values)

                            # craft pdu response
                            pdu = struct.pack('>BB', fc, 2*numValues) + valuesBytes
                    
                elif fc in (writeInputRegisters, writeHoldingRegisters):
                    (adrs, numInputs, valueVec) = mbstruct.unpack_write_registers_pdu(pdu_in)
                    if tablesize < adrs+numInputs+1:
                        # err = True
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        if fc==writeInputRegisters:
                            setTableValues(inputRegblock, adrs, valueVec) 
                        else:
                            setTableValues(holdingRegblock, adrs, valueVec) 

                        pdu = struct.pack('>BHH', fc, adrs, numInputs)

                elif fc in (writeInputRegister, writeHoldingRegister):
                    (adrs, value) = struct.unpack('>HH', pdu_in[:4])
                    if tablesize <= adrs:
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        if fc==writeInputRegister:
                            setTableValues(inputRegblock, adrs, [value])
                        else:
                            setTableValues(holdingRegblock, adrs, [value])

                        pdu = struct.pack('>BHH', fc, adrs, value)
                
                elif fc == maskWriteRegister:
                    (adrs, andMsk, orMsk) = struct.unpack('>HHH', pdu_in[:6])
                    if tablesize <= adrs:
                        pdu = struct.pack('>BB', 0x80+fc, 2)
                    else:
                        OK, regValue = getTableValues(holdingRegblock, adrs, 1)
                        if not OK:
                            pdu = struct.pack('>BB', 0x80+fc, 2)
                        else:
                            regValue[0] &= andMsk
                            regValue[0] |= orMsk
                            OK = setTableValues(holdingRegblock, adrs, regValue)
                            if not OK:
                                pdu = struct.pack('>BB', 0x80+fc, 2)
                            else:
                                pdu = struct.pack('>BHHH', fc, adrs, andMsk, orMsk)

                elif fc == readWriteRegisters:
                    (readAdrs, readNum, writeAdrs, writeNum, writeBytes) = struct.unpack('>HHHHB', pdu_in[:9])
                    writeValues = mbstruct.unpack_values_list(pdu_in[9:])
                    OK = setTableValues(holdingRegblock, writeAdrs, writeValues)
                    if not OK:
                        pdu = struct.pack('>BB', 0x80+fc, 4)
                    else: 
                        OK, values = getTableValues(holdingRegblock, readAdrs, readNum)
                        if not OK:
                            pdu = struct.pack('>BB', 0x80+fc, 4)
                        else:
                            valuesBytes = mbstruct.make_values_list(values)

                            # craft pdu response
                            pdu = struct.pack('>BB', fc, 2*readNum) + valuesBytes

                elif fc in unsupportedFuncs:
                    print("Function code ({fc}) presently unsupported by this server")
                    continue

                else:
                    # create an error response flagging illegal function
                    pdu = struct.pack('BB', fc+0x80, 0x1)

            # the response has generated a pdu, which is now packaged with information needed 
            # for a modbus message header to create a complete message
            #
            modbus_packet = create_modbus_tcp_packet(transID, unitID, pdu)

            # validate the message.  Should be fine because this code constructed it, but perhaps
            # a malicious insider tinkered with it
            valid, excpCode = mbaux.valid_modbus_msg(modbus_packet, False, True, extended)
            if not valid and excpCode ==0:
                continue
            elif not valid:
                print("error: invalid response message ({modbus_packet}) created")
                pdu = struct.pack('BB', fc+0x80, excpCode)
                modbus_packet = create_modbus_tcp_packet(transID, unitID, pdu)
            
            # send the response back to the client 
            conn.sendall(modbus_packet)  
            # end of the loop, so go back and wait for another request


def create_modbus_tcp_packet(transaction_id, unit_id, pdu):
    """
    Manually constructs a Modbus TCP packet.
    :param transaction_id: 16-bit transaction identifier.
    :param unit_id: 8-bit unit identifier.
    :param function_code: 8-bit Modbus function code.
    :param pdu: Bytes representing the PDU 
    :return: Bytes representing the complete Modbus TCP packet.
    """
    protocol_id = 0  # Modbus protocol identifier (fixed at 0 for Modbus TCP)

    # MBAP Header: Transaction ID (2 bytes), Protocol ID (2 bytes), Length (2 bytes), Unit ID (1 byte)
    mbap_header = struct.pack('>HHHB', transaction_id, protocol_id, len(pdu)+1, unit_id)

    return mbap_header + pdu


def setup_server(tablesize, server_host, client_port):
    global srvr_sock, coilblock, datablock, inputRegblock, holdingRegblock
    """Run server setup."""

    coilblock       = ModbusSequentialDataBlock(0x00, [0]*tablesize)
    datablock       = ModbusSequentialDataBlock(0x00, [0]*tablesize)
    inputRegblock   = ModbusSequentialDataBlock(0x00, [0]*tablesize)
    holdingRegblock = ModbusSequentialDataBlock(0x00, [0]*tablesize)

    # spin up the srvr socket
    srvr_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srvr_sock.bind((server_host, client_port))
    print(f"listening for client on ({server_host}, {client_port})") 

