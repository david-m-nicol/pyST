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
import argparse
import plc
import dt
import mbs
import time

# default milliseconds per dt clock tick
mpt = 5000

# default milliseconds per plc cycle
mpc = 100

client_port = None
server_host = '127.0.0.1'

tablesize = 100

transactionID = 1
rseed = 123455

def getArgs():
    global client_port, dt_port, server_host, dt_host, tablesize, mpt, mpc, rseed

    parser = argparse.ArgumentParser()

    parser.add_argument(u'-shost', metavar = u'server host', 
                        dest=u'server_host', required=False)

    parser.add_argument(u'-cport', metavar = u'modbus client port ', 
                        dest=u'client_port', required=True)

    parser.add_argument(u'-tablesize', metavar = u'length of PyModbus data tables', 
                        dest=u'tablesize', required=False)

    parser.add_argument(u'-mpc', metavar = u'milliseconds per cycle', 
                        dest=u'mpc', required=False)

    parser.add_argument(u'-seed', metavar = u'random seed', 
                        dest=u'rseed', required=False)

    # check whether what we want to do is read from a configuration file
    cmdline = []
    if sys.argv[1] == '-is':
        with open(sys.argv[2], 'r') as rf:
            for line in rf:
                line = line.strip()
                if len(line) == 0 or line.startswith('#'):
                    continue
                cmdline.extend(line.split())
    else:
        cmdline = sys.argv[1:]

    args = parser.parse_args(cmdline)

    if not args.client_port.isdigit():
        print("server port number must be integer")
        exit(1)

    client_port = int(args.client_port)
    if not 1024 <= client_port <= 49151:
        print("client port number should be in [1024, 49151]")
        exit(1)

    if args.server_host is not None:
        server_host = args.server_host
    else:
        server_host = '127.0.0.1'

    if args.tablesize is not None:
        try:
            try_tablesize = int(args.tablesize)
            if not 1 <= try_tablesize <= 65355:
                print(f"block size [{try_tablesize}] should be an integer in [1, 65355], using default {tablesize}")
            else:
                tablesize = try_tablesize
        except:
                print(f"block size [{try_tablesize}] should be an integer in [1, 65355], using default {tablesize}")

    if args.mpc is not None:
        try:
            mpc = int(args.mpc)
            if mpc < 0:
                print(f"milliseconds per cycle needs to be non-negative")
                exit(1)
        except:
            print(f"milliseconds per cycle needs to be non-negative")
            exit(1)

    mpt = 5*mpc    

    if args.rseed is not None:
        rseed = int(args.rseed)

def main(cmdline):
    global tablesize, server_host, client_port

    """Combine setup and run."""
    args = getArgs()

    # set up the asychronous pymodbus server
    mbs.setup_server(tablesize, server_host, client_port)
    
    srvr_thread = threading.Thread(target=mbs.srvr_thread_function, args=(mbs.srvr_sock, False))
    srvr_thread.start()

    # spin up the PLC thread
    plc_thread = threading.Thread(target=plc.plc_thread_function, args=(mpc,))
    plc_thread.start()

    # spin up the digital twin thread
    dt_thread = threading.Thread(target=dt.dt_thread_function, args = (mpt,rseed))
    dt_thread.start()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("run-time arguments needed")
        exit(1)
    main(sys.argv[1:])
