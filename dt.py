#!/usr/bin/env python3
import sys
import pdb
import time
import os
import threading
import random
import plc
import hashlib

# indices for discrete input table (IX)
on_idx = 0
F0_req_idx = 1
F1_req_idx = 2
F2_req_idx = 3
F3_req_idx = 4

door_closed_idx = 5 
moving_up_idx = 6
moving_down_idx = 7
di_end = moving_down_idx+1

# indices for input registers table (IW)
ir_pos_idx = 0
ir_end = ir_pos_idx+1

# indices for coil table (QX)
sys_on_idx = 0
open_cmd_idx = 1
close_cmd_idx = 2
move_up_cmd_idx = 3
move_down_cmd_idx = 4
coil_end = move_down_cmd_idx+1

# indices for holding registers table (MW)
hr_ticks_per_flr_idx  = 1
hr_msec_per_tick_idx = 2
hr_end = hr_msec_per_tick_idx+1

discrete_input = [False]*di_end
discrete_input[on_idx] = False


# door is initially closed
discrete_input[ door_closed_idx ] = True

coil     = [False]*coil_end

holding_reg     = [0]*hr_end
holding_reg[ hr_ticks_per_flr_idx ] = 4
input_reg       = [0]*ir_end


def coil_sig(coil):
    byte_string = b''.join(str(item).encode('utf-8') for item in coil)
    sha256_hash = hashlib.sha256(byte_string).hexdigest()
    return sha256_hash

old_sig = coil_sig(coil)

def dt_thread_function(msec_per_tick, rseed):
    global discrete_input, input_reg, holding_reg, coil, old_sig

    count_down = 0

    # write out the initial state of the discrete inputs, the 
    # sequence from 0 to the end of the table
    write_IX(0, di_end-1, discrete_input)

    # write out the initial state of the input registers table
    write_IW(0, ir_end-1, input_reg)

    # write out the initial state of the holding registers table
    write_MW(0, hr_end-1, holding_reg)

    flr = 0
    up_direction = True
    position = input_reg[ir_pos_idx]

    random.seed(rseed)

    # start the simulation with an initial door ask
    new_flr = flr
    while new_flr == flr:
        new_flr = random.randint(0,3)  

    discrete_input[ F0_req_idx + new_flr ] = True 

    # enter a loop that advances each time-step
    while True:
        # wait this long, and then do stuff
        time.sleep(msec_per_tick/1000)
        open_door_evt = False

        # advance position by ts_per_tick
        old_position = position
        if (discrete_input[moving_up_idx] or discrete_input[moving_down_idx]):
            position += (1 if up_direction else -1)

        # read in the command coils
        OK, coil = read_QX(0, coil_end-1)

        new_sig = coil_sig(coil)
        changed_sig = (new_sig != old_sig)
        old_sig = new_sig

        if not OK:
            print("Problem reading coil inputs")
            continue
 
        # if the system is on, compute new state 
        if coil[0]:

            discrete_input[ on_idx ] = True

            # get state to reflect directives r.e. power
            discrete_input[ moving_up_idx ]  = coil[ move_up_cmd_idx ] 
            discrete_input[ moving_down_idx ] = coil[ move_down_cmd_idx ] 

            if not coil[ move_up_cmd_idx ] and not coil[ move_down_cmd_idx ]:
                if changed_sig and old_position != position:
                    print(f"power stopped at position {position}")

            # close the door if so directed and the door is not already closed
            if coil[ close_cmd_idx ] and not discrete_input[ door_closed_idx ]:
                if changed_sig:
                    print(f"door closes at position {position}")
                doorClosed = True
                discrete_input[ door_closed_idx ] = True

            # open the door if directed and the door is closed, which clears the state and clears the request
            elif coil[ open_cmd_idx ] and discrete_input[ door_closed_idx ]:
                # open the door
                doorClosed = False
                discrete_input[ door_closed_idx ] = False

                if changed_sig:
                    print(f"door opens at position {position}")

                # remember that the door transitioned from closed to open at this step
                open_door_evt = True

                # clear request in car if present 
                flr = int(input_reg[ ir_pos_idx ]/4)
                discrete_input[ F0_req_idx + flr ] = False

            # check whether motion is started
            if coil[ move_up_cmd_idx ]:
                discrete_input[ moving_up_idx ] = True
                up_direction = True

                if changed_sig:
                    print(f"start moving up from position {position}")

            elif coil[ move_down_cmd_idx ]:
                discrete_input[ moving_down_idx ] = True
                up_direction = False

                if changed_sig:
                    print(f"start moving down from position {position}")

            # batch all the writes here at the end of the cycle so that 
            # the actions during the cycle are completely driven by 
            # the state at the beginning of the cycle and the coils read
            # at the beginning of the cycle

            # report the new position 
            input_reg[ir_pos_idx] = position
            write_IW(0, ir_end-1, input_reg)

            # if the door just opened, randomly choose another floor to visit which is not the one
            # we're presently at
            if open_door_evt:
                new_flr = flr
                while new_flr == flr:
                    new_flr = random.randint(0,3)  

                discrete_input[ F0_req_idx + new_flr ] = True 
                print(f"door requests {discrete_input[F0_req_idx:F0_req_idx+4]}")

            # report the discrete input states
            write_IX(0, di_end-1, discrete_input)


def read_QX(first, last):
    OK, values = plc.QX_seq.read_values(first, last)
    if not OK:
        print(f"read_QX from {first} to {last} failed")
        return []
    return True, values

def read_QW(first, last):
    OK, values = plc.QW_seq.read_values(first, last)
    if not OK:
        print(f"read_QW from {first} to {last} failed")
        return []
    return True, values


def write_IX(first, last, values):
    OK = plc.IX_seq.write_values(first, last, values)
    if not OK:
        print(f"write_IX from {first} to {last} failed")

def write_IW(first, last, values):
    OK = plc.IW_seq.write_values(first, last, values)
    if not OK:
        print(f"write_IW from {first} to {last} failed")

def write_MW(first, last, values):
    OK = plc.MW_seq.write_values(first, last, values)
    if not OK:
        print(f"write_MW from {first} to {last} failed")

