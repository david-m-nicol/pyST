import socket
import mbstruct
import struct
import sys
import pdb
import time
import threading

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

transID = 1
client_socket = None

def open_modbus_socket(host, port, wait=0):
    print(f"open socket to {host}:{port}")

    while True:
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((host, port))
            print(f"connected to {host}:{port}")
            return client_socket
        except socket.error as e:
            if wait <=0 :
                print(f"Socket error: {e}")
                return None
            else:
                time.sleep(1)
                wait -= 1

valid_req_fc = (0x1, 0x2, 0x3, 0x4, 0x5, 0x6, 0xF, 0x10, 0x14, 0x15, 0x16, 0x17, 0x18, 0x2B)
valid_extd_req_fc = (writeDiscreteInputs, writeDiscreteInput, writeInputRegisters, writeInputRegister)
valid_req_serial_fc = (0x7, 0x8, 0xB, 0xC, 0x11)


valid_rsp_fc = (0x81, 0x82, 0x83, 0x85, 0x86, 0x87, 0x88, 0x8B, 0x8C, 0x8F, 0x90, 0x91, 0x94, 0x95, 0x96, 0x97, 0x98, 0xAB)
valid_rsp_serial_fc = (0x87, 0x88, 0x8B, 0x8C, 0x91)
valid_extd_rsp_fc = (0x80+writeDiscreteInputs, 0x80+writeDiscreteInput, 0x80+writeInputRegisters, 0x80+writeInputRegister)


# check validity of message purported to be a modbus message
def valid_modbus_msg(msg, request, tcp, extended):
    try:
        (transID, protID, msgLen, unitID) = struct.unpack('>HHHB', msg[:7])
    except:
        print(f"error: modbus header misformed")
        return False, 0

    observedLen = len(msg)
    if observedLen != msgLen+6:
        print(f"error: modbus message misformed, length fault")
        return False, 0

    # get the function code
    fc = msg[7]

    if not tcp:
        if request and fc not in valid_req_fc and fc not in valid_req_serial_fc:
            if not extended or fc not in valid_extd_req_fc:
                print(f"error: request function code {fc} not valid")
                return False, 0

        if not request and fc not in valid_req_fc and fc not in valid_rsp_fc and fc not in valid_rsp_serial_fc:
            if not extended or (fc not in valid_extd_req_fc and fc not in valid_extd_rsp_fc):
                print(f"error: response function code {fc} not valid")
                return False, 0
    else:
        if request and fc not in valid_req_fc: 
            if not extended or fc not in valid_extd_req_fc:
                print(f"error: request function code {fc} not valid")
                return False, 0

        if not request and fc not in valid_req_fc and fc not in valid_rsp_fc: 
            if not extended or (fc not in valid_extd_req_fc and fc not in valid_extd_rsp_fc):
                print(f"error: response function code {fc} not valid")
                return False, 0


    pdu = msg[8:]

    # check read request
    if request:
        if fc in (0x01, 0x02, 0x03, 0x04):
            try:
                (adrs, number) = struct.unpack('>HH', pdu)
                # check address
                if adrs < 0:
                    print(f"error: ({fc}) request address must be non-negative")
                    return False, 2

                if number < 0:
                    print(f"error: ({fc}) request number to read is negative")
                    return False, 3
            except:
                print(f"error: ({fc}) request pdu ill-formed")
                return False, 0

        # check single write request
        elif fc in (0x5, 0x6):
            try:
                (adrs, value) = struct.unpack('>HH', pdu)
                # check address
                if adrs < 0:
                    print(f"error: ({fc}) request address must be non-negative")
                    return False, 2
            except:
                print(f"error: ({fc}) request pdu ill-formed")
                return False, 0

        # multiple writes  
        elif fc in (0xF, 0x10):
            try:
                (adrs, number, writeBytes) = struct.unpack(">HHB", pdu[:5])
                # check address
                if adrs < 0:
                    print(f"error: ({fc} request address must be non-negative")
                    return False, 2

                if writeBytes != len(pdu[5:]):
                    print(f"error: ({fc}) request pdu ill-formed")
                    return False, 0

            except:
                print(f"error: ({fc}) request pdu ill-formed")
                return False, 0

        elif fc==0x016:
            try:
                (adrs, andMsk, orMsk) = struct.unpack(">HHH", pdu)
                if adrs< 0:
                    print(f"error: ({fc}) address must be non-negative")
                    return False, 2

            except:
                print(f"error: ({fc}) request pdu ill-formed")
                return False, 0

        elif fc==0x17:
            try:
                (readAdrs, readNum, writeAdrs, writeNum, writeBytes) = struct.unpack('>HHHHB', pdu[:9])
                if readAdrs < 0 or writeAdrs < 0:
                    print(f"error: ({fc}) request address must be non-negative")
                    return False, 2
                # figure bytes to write
                if writeBytes != len(pdu[9:]):
                    print(f"error: ({fc}) request pdu ill-formed")
                    return False, 0

            except:
                print("({fc}) request pdu ill-formed")
                return False, 0

    else:
        if fc in (0x01, 0x02, 0x03, 0x04):
            try:
                byteCount = pdu[0]
                if byteCount != len(pdu[1:]):
                    print(f"error: ({fc}) response pdu ill-formed")
                    return False, 0
            except:
                print(f"error: ({fc}) response pdu ill-formed")
                return False, 0

        elif fc in (0x81, 0x82, 0x83, 0x84):
            if not valid_exception(fc, pdu):
                return False, 1

        # check single write request
        elif fc in (0x5, 0x6):
            try:
                (adrs, value) = struct.unpack('>HH', pdu)
                # check address
                if adrs < 0:
                    print(f"error: ({fc}) response address must be non-negative")
                    return False, 2
            except:
                print(f"error: ({fc}) response pdu ill-formed")
                return False, 0

        elif fc in (0x85, 0x86):
            if not valid_exception(fc,pdu):
                return False, 1

        # multiple writes  
        elif fc in (0xF, 0x10):
            try:
                (adrs, number) = struct.unpack(">HH", pdu)
                # check address
                if adrs < 0:
                    print(f"error: ({fc}) response address must be non-negative")
                    return False, 2

                if number < 1:
                    print(f"error: ({fc}) response pdu ill-formed")
                    return False, 0
            except:
                print(f"error: ({fc}) response pdu ill-formed")
                return False, 0

        elif fc in (0x8F, 0x90):
            if not valid_exception(fc,pdu):
                return False, 1

        elif fc==0x16:
            try:
                (adrs, andMsk, orMsk) = struct.unpack(">HHH", pdu)
                if adrs< 0:
                    print(f"error: address must be non-negative")
                    return False, 2

            except:
                print(f"error: ({fc}) response pdu ill-formed")
                return False, 0

        elif fc==0x96:
            if not valid_exception(fc,pdu):
                return False, 1
            
        elif fc==0x17:
            try:
                readBytes = struct.unpack('B', pdu[:1])
                if readBytes != len(pdu[1:]):
                    print(f"error: ({fc}) response pdu ill-formed")
                    return False, 0
            except:
                print(f"error: ({fc}) response pdu ill-formed")
                return False, 0
            
        elif fc== 0x97:
            if not valid_exception(fc,pdu):
                return False, 1
    return True, 0


def valid_exception(fc, pdu):
    excCode = struct.unpack("B", pdu)
    if excCode[0] not in (0x1, 0x2, 0x3, 0x4):
        print(f"error: ({fc}) response pdu ill-formed")
        return False
    return True
                
# send a message already in bytes form
def send_modbus_msg(mbs, msg, updateTransID=True, fullReturn=False, timeout=10.0):
    global transID

    # use current transID
    if updateTransID:
        msg = struct.pack('>H', transID) + msg[2:]
        transID += 1

    fc = msg[7]
    if mbs is not None:
        try:
            mbs.sendall(msg)
        except Exception as e: 
            print(f"sendall returns exception {e}")
            return False, None
 
        if timeout is not None:
            mbs.settimeout(timeout)
            try:
                data = mbs.recv(512)
            except socket.timeout:
                print(f"socket receive timeout after {timeout} seconds")
                return False, None
            except Exception as e:
                print(f"socket receive error")
                return False, None 
        else:
            data = mbs.recv(512)
    else:
        print("socket is absent")
        return False, None

    # function code is first byte of pdu,
    # if error will not be the same as the request
    rtn_fc = data[7]
    if fc != rtn_fc:
        print(f"error returned, fc {fc} != return fc {rtn_fc} in data {data}")
        if 9 <= len(data): 
            return False, data[8:9]
        else:
            return False, 0x00

    # return a bytes object of the pdu after the function code
    if fullReturn:
        return True, data
    else:
        return True, data[8:]
    
# create a request to write a vector of bits, passed in as a list
# of booleans.
#
def writeBitsMsg(fc, adrs, bits, deviceID):
    numBits = len(bits)

    # turn the vector of bools into a sequence of bitcodes
    bitVec = mbstruct.make_bitmask_list(bits)

    # craft the PDU
    pdu = struct.pack('>BHHB', fc, adrs, numBits, len(bitVec)) + bitVec  

    # header depends on the length of the pdu
    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)

    return hdr + pdu

def write_DiscreteInputsMsg(adrs, bits, deviceID):
    return writeBitsMsg(writeDiscreteInputs, adrs, bits, deviceID)

def write_CoilsMsg(adrs, coils, deviceID):
    return writeBitsMsg(writeCoils, adrs, coils, deviceID)

# write a list of values to registers, carried as a list of integers
# in the values list.  Used to read from the holding and input register files
def writeRegistersMsg(fc, adrs, values, deviceID):
    numValues = len(values)

    # turn the list of integers in to bytes object, each entry in 2-byte big-endian form
    valuesVec = mbstruct.make_values_list(values)

    pdu = struct.pack('>BHHB', fc, adrs, numValues, 2*numValues)
    pdu = pdu + valuesVec

    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def write_HoldingRegistersMsg(adrs, values, deviceID):
    return writeRegistersMsg(writeHoldingRegisters, adrs, values, deviceID)

def write_InputRegistersMsg(adrs, values, deviceID):
    return writeRegistersMsg(writeInputRegisters, adrs, values, deviceID)

def write_HoldingRegisterMsg(adrs, value, deviceID):
    return writeRegistersMsg(writeHoldingRegisters, adrs, [value], deviceID)

def write_InputRegisterMsg(adrs, value, deviceID):
    return writeRegistersMsg(writeInputRegisters, adrs, [value], deviceID)

def write_MaskRegisterMsg(adrs, andMsk, orMask, deviceID):
    pdu = struct.pack('>BHHH', maskWriteRegister, adrs, andMsk, orMask)

    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def read_WR_RegistersMsg(readAdrs, readNum, writeAdrs, writeNum, values, deviceID):
    # turn the list of integers in to bytes object, each entry in 2-byte big-endian form
    valuesVec = mbstruct.make_values_list(values)

    pdu = struct.pack('>BHHHHB', readWriteRegisters, readAdrs, readNum, writeAdrs, writeNum, len(valuesVec))
    pdu = pdu + valuesVec

    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

# read a list of one bit entities, used to read coils and discrete inputs
def readBitListMsg(fc, adrs, numBits, deviceID):
    pdu = struct.pack('>BHH', fc, adrs, numBits)
    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def readBitListRtn(rtn, bits):
    numBits = bits
    numBytes = rtn[0]
    rtn = rtn[1:]
    values = []
    while numBits > 0:
        for bits in rtn:
            bitMsk = 0x01
            for pos in range(0, min(8, numBits)):
                values.append(True if bitMsk & bits else False)
                numBits -= 1
                bitMsk <<= 1

    return values

# read a list of register values, used to read holding and input registers
def readValueListMsg(fc, adrs, numValues, deviceID):
    pdu = struct.pack('>BHH', fc, adrs, numValues)
    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def readValueListRtn(rtn):
    numBytes = rtn[0]
    rtn = rtn[1:]
    values  = []
    while numBytes > 0:
        value = struct.unpack('>H', rtn[:2])
        values.append(value[0])
        rtn = rtn[2:]
        numBytes -= 2

    return values

def read_CoilsMsg(adrs, numCoils, deviceID):
    return readBitListMsg(readCoils, adrs, numCoils, deviceID)

def read_CoilsRtn(rtn, coils):
    return readBitListRtn(rtn, coils)

def read_DiscreteInputsMsg(adrs, numInputs, deviceID):
    return readBitListMsg(readDiscreteInputs, adrs, numInputs, deviceID)

def read_DiscreteInputsRtn(rtn, bits):
    return readBitListRtn(rtn, bits)

def read_HoldingRegistersMsg(adrs, numRegs, deviceID):
    return readValueListMsg(readHoldingRegisters, adrs, numRegs, deviceID)

def read_HoldingRegistersRtn(rtn):
    return readValueListRtn(rtn)

def read_InputRegistersMsg(adrs, numRegs, deviceID):
    return readValueListMsg(readInputRegisters, adrs, numRegs, deviceID)

def read_InputRegistersRtn(rtn):
    return readValueListRtn(rtn)

def readBitMsg(fc, adrs, deviceID):
    pdu = struct.pack('>BH', fc, adrs)
    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def readBitRtn(rtn):
    rtnValue = struct.unpack('>H', rtn[2:])
    rtnBool = True if rtnValue[0] > 0 else False
    return rtnBool

def read_DiscreteInputMsg(adrs, deviceID):
    return readBitMsg(readDiscreteInputs, adrs, deviceID)

def read_DiscreteInputRtn(rtn):
    return readBitRtn(rtn)

def read_CoilMsg(adrs, deviceID):
    return readBitMsg(readDiscreteInputs, adrs, deviceID)

def read_CoilRtn(rtn):
    return readBitRtn(rtn)

def writeBitMsg(fc, adrs, bit, deviceID):
    bitCode = 0xFF00 if bit else 0x00
    pdu = struct.pack('>BHH', fc, adrs, bitCode)
    hdr = struct.pack('>HHHB', transID, 0, len(pdu)+1, deviceID)
    return hdr + pdu

def write_DiscreteInputMsg(adrs, bit, deviceID):
    return writeBitMsg(writeDiscreteInput, adrs, bit, deviceID)

def write_CoilMsg(adrs, bit, deviceID):
    return writeBitMsg(writeCoil, adrs, bit, deviceID)


