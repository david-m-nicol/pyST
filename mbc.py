#!/usr/bin/env python3
import socket
import mbstruct
import mbaux
import struct
import sys
import pdb
import argparse
import time
import queue
import os
import threading

server_port = None
server = None
delay  = 2
in_on = 0

# indices for discrete input table
di_srt = 0
state_idx = di_srt
door_closed_idx = di_srt+1
moving_idx = di_srt+2
di_end = di_srt+3

# indices for input registers
ir_srt = 0
current_flr_idx = ir_srt
ms_to_close_idx = ir_srt+1
req_flr_idx = ir_srt+2
ir_end = req_flr_idx + 4

# indices for coil table
coil_srt = 0
on_idx = coil_srt
coil_end = on_idx+1

# indices for holding registers
hr_srt = 0
tgt_flr_code_idx = hr_srt
hr_end = hr_srt+1

discrete_input         = [False]*di_end
discrete_input[on_idx] = False
coil                   = [False]*coil_end
input_reg              = [0]*ir_end
holding_reg            = [0]*hr_end

sec_per_tick = 1

def getArgs():
    parser = argparse.ArgumentParser()

    parser.add_argument(u'-port', metavar = u'modbus port', dest=u'port', required=True)

    cmdline = []

    # open the file of command line arguments
    if len(sys.argv) == 2:
        with open(sys.argv[1],"r") as rf:
            for line in rf:
                line = line.strip()
                # skip empty lines or comment lines
                if len(line) == 0 or line.startswith('#'):
                    continue
                # take everything on the line as words from the command line
                cmdline.extend(line.split())

    else:
        cmdline = sys.argv[1:]

    # fetch the (many) arguments
    args = parser.parse_args(cmdline)
    return args


def checkArgs(args):
    global server_port

    err = False 

    if not args.port.isdigit():
        print("error: modbus port must be integer")
        err = True 
    
    server_port = int(args.port)
    return err

deviceID = 1

def reportErrRtn(fc, excpt, msg=""):
    print(f"Error returned (function code {fc}, exception {excpt}) {msg}")
    return

def main():
    global delay

    # get the input arguments, exit on an error
    args = getArgs()
    argError = checkArgs(args)
    if argError:
       exit(1)

    mbs = None
    # try to open the modbus socket to the server, wait up to 60 seconds.

    mbs = mbaux.open_modbus_socket('127.0.0.1', server_port, 60)
    if mbs is None:
        print(f"unable to open socket {server}:{server_port})")
        exit(1)

    # Start digital twin update thread
    dt_thread = threading.Thread(target=dt_thread_function, args=(mbs,))
    dt_thread.start()

def dt_thread_function(mbs):
    global discrete_input, input_reg, coil, holding_reg

    # wait 10 seconds before sending a message to raise the sys_on coil
    time.sleep(5)

    reqMsg = mbaux.write_CoilMsg(on_idx, 1, deviceID)
    OK, rtn = mbaux.send_modbus_msg(mbs, reqMsg, True)

    if not OK:
        reportErrRtn(reqMsg[8], rtn, "failure to write system on coil")
        exit(1)


    logic_state = 0
    tgt_flr_code = 0
    tgt_flr = 0

    # enter a loop where we sleep for 2 seconds, then acquire the discrete input, input registers, and holding registers
    while True:
        time.sleep(2)

        num_discrete_inputs = di_end-di_srt

        reqMsg = mbaux.read_DiscreteInputsMsg(di_srt, num_discrete_inputs, deviceID)
        OK, rtn = mbaux.send_modbus_msg(mbs, reqMsg, True)
        if OK:
            discrete_input = mbaux.read_DiscreteInputsRtn(rtn, num_discrete_inputs)
        else: 
            reportErrRtn(reqMsg[8], rtn, "failure to read discrete inputs")
            exit(1)

        num_input_reg = ir_end-ir_srt
        reqMsg = mbaux.read_InputRegistersMsg(ir_srt, num_input_reg, deviceID)
        OK, rtn = mbaux.send_modbus_msg(mbs, reqMsg, True)
        if OK:
            input_reg = mbaux.read_InputRegistersRtn(rtn)
        else: 
            reportErrRtn(reqMsg[8], rtn, "failure to read input registers")
            exit(1)

        num_holding_reg = hr_end-hr_srt
        reqMsg = mbaux.read_HoldingRegistersMsg(hr_srt, num_holding_reg, deviceID)
        OK, rtn = mbaux.send_modbus_msg(mbs, reqMsg, True)
        if OK:
            holding_reg = mbaux.read_HoldingRegistersRtn(rtn)
        else: 
            reportErrRtn(reqMsg[8], rtn, "failure to read holding registers")
            exit(1)

        sys_state = discrete_input[ state_idx ]
        door_closed = discrete_input[ door_closed_idx ]
        is_moving = discrete_input[ moving_idx ]
      
        current_flr      = input_reg[ current_flr_idx ]  
        ms_to_close      = input_reg[ ms_to_close_idx ]
        req_flr          = input_reg[ req_flr_idx:req_flr_idx+4 ]
        obs_tgt_flr_code = holding_reg[ tgt_flr_code_idx ]

        print(f"mbc sys_state {sys_state}, floor {current_flr}, door_closed {door_closed}, moving {is_moving}") 
        print(f"\treq_flr {req_flr}\n")

        match logic_state:
            case 0:
                # await the elevator to have a closed door, not be moving 
                if door_closed and not is_moving:
                    # transition to waiting for some floor to be requested
                    logic_state = 1
            case 1:
                # gather up the floor requests
                requested = []
                for idx in range(0,4):
                    if req_flr[idx]:
                        requested.append(idx)

                # if at least one floor is requested, pick the one
                # closest to the present floor
                if len(requested) > 1:
                    nxt_floor = -1
                    min_dist = 5

                    for rf in requested:
                        if abs(rf-current_flr) < min_dist:
                            nxt_floor = rf
                            min_dist = abs(rf-current_flr)

                    holding_reg[ tgt_flr_code_idx ] = nxt_floor+1
                    tgt_flr = nxt_floor
                    print(f"choose next flr {tgt_flr}")

                    tgt_flr_code = tgt_flr+1
                    logic_state = 2             
                elif len(requested) == 1:
                    tgt_flr = requested[0]
                    print(f"choose next flr {tgt_flr}")
                    holding_reg[ tgt_flr_code_idx ] = tgt_flr+1
                    tgt_flr_code = requested[0]+1
                    logic_state = 2             

            case 2:
                # await recognition that floor was noticed.  
                if tgt_flr_code == obs_tgt_flr_code and tgt_flr_code > 0:
                    tgt_flr_code = 0
                    holding_reg[ tgt_flr_code_idx ] = 0 
                    logic_state = 3


            case 3:
                # await recognition that the floor selection clear was observed
                if obs_tgt_flr_code == 0 and not is_moving:
                    logic_state = 0


        # write the selected floor                 
        reqMsg = mbaux.write_HoldingRegistersMsg(hr_srt, [tgt_flr_code], deviceID)

        OK = mbaux.send_modbus_msg(mbs, reqMsg, True)
        if not OK:
            reportErrRtn(reqMsg[8], rtn, "failure to write holding registers")
            exit(1)
         
          
if __name__ == "__main__":
    main()


