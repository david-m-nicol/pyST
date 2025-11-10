import struct
import pdb
import logging

_logger = logging.getLogger(__name__)

# the first five bytes in the passed argument identify the starting address,
# the number of bits being represented, and the number of bytes being used
# to implement the representation.   Returned is the starting address,
# the number of bits represented, and a list of booleans representing the encoded bits
def unpack_bits_pdu(msg):
    adrs, num_bits, num_bytes = struct.unpack('>HHB',msg[:5])
    # turn the bits into a list of bools

    codes = []
    bits = msg[5:]
    cnt_bits = num_bits

    for bitByte in bits:
        msk = 0x01
        for pos in range(0,8):
            if cnt_bits == 0:
                break
            if msk & bitByte:
                codes.append(True)
            else:
                codes.append(False)
            msk = msk << 1
            cnt_bits -= 1

    return adrs, num_bits, codes


# PDU header when a list of values is passed to be written into registers. Extract and return
# the starting address, the number of registers, and a list of values
# associated with those registers 
#
def unpack_write_registers_pdu(msg):
    adrs, num_regs, byte_cnt = struct.unpack('>HHB', msg[:5])
    values = []
    regs = msg[5:]
    for pos in range(0, num_regs):
        vt = struct.unpack('>H', regs[:2])
        values.append(vt[0])
        regs = regs[2:]

    return adrs, num_regs, values

# PDU header when a list of registers is passed to be read from.  Extract and return
# the starting address, the number of registers
def unpack_read_registers_pdu(msg):
    return struct.unpack('>HH', msg[:5])

# PDU header when a list of registers is passed to be written to.  Extract and return
# the starting address, the number of registers, and return a list of 16-bit values to write
def unpack_write_registers_pdu(msg):
    adrs, numValues, numBytes = struct.unpack('>HHB', msg[:5])

    values = []
    for idx in range(5, 5+2*numValues, 2):
        value = struct.unpack('>H', msg[idx:idx+2])
        values.append(value[0])

    return adrs, numValues, values

# codes is list of bools.  Return bytes object with
# list of encoded bits
def make_bitmask_list(codes):
    lenCodes = len(codes)
    numCodes = int(lenCodes/8)
    if lenCodes%8 != 0:
        numCodes += 1

    codePos = 0
    for code in range(0,numCodes):
        bitByte = 0x0
        for pos in range(codePos, min(codePos+8, lenCodes)):
            if pos%8 == 0:
                msk = 0x01
            if codes[pos]:
                bitByte |= msk
            msk <<= 1

        if code==0:
            rtn = struct.pack('B', bitByte)
        else:
            rtn = rtn + struct.pack('B', bitByte)
        codePos += 8

    return rtn

# list of integers is passed as argument.   Return bytes object
# encoding that list as a sequence of 16-bit integer values
def make_values_list(values):
    rtn = struct.pack('>H', values[0])
    for pos in range(1,len(values)):
        rtn = rtn + struct.pack('>H', values[pos])

    return rtn

def unpack_values_list(values):
    vList = []
    bytesToParse = len(values)
    while bytesToParse > 0:
        value = struct.unpack('>H', values[:2])
        vList.append(value[0])
        values = values[2:]
        bytesToParse -= 2
    return vList

