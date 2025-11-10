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
moving_idx = di_srt+1
di_end = moving_idx+1

# indices for input registers
ir_srt = 0
logic_idx = ir_srt
floor_level_idx = ir_srt+1
target_level_idx = ir_srt+2
ir_end = target_level_idx+1

# indices for coil table
coil_srt = 0
on_idx = coil_srt
coil_end = on_idx+1

discrete_input         = [False]*di_end
discrete_input[on_idx] = False
coil                   = [False]*coil_end

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
    global discrete_input, input_reg, coil

    # wait 10 seconds before sending a message to raise the sys_on coil
    time.sleep(5)

    reqMsg = mbaux.write_CoilMsg(on_idx, 1, deviceID)
    OK, rtn = mbaux.send_modbus_msg(mbs, reqMsg, True)

    if not OK:
        reportErrRtn(reqMsg[8], rtn, "failure to write system on coil")
        exit(1)


    # enter a loop where we sleep for 2 seconds, then acquire the input and input registers
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

        sys_state = discrete_input[ state_idx ]
        is_moving = discrete_input[ moving_idx ]
          
        srv_state = input_reg[ logic_idx ]
        flr_level = input_reg[ floor_level_idx ]
        tgt_level = input_reg[ target_level_idx ]
       
        print(f"sys_on {sys_state}, moving {is_moving}");
        print(f"srv_state {srv_state}, floor level {flr_level}, target level {tgt_level}\n")
          
if __name__ == "__main__":
    main()


