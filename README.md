



#### pyST

### Overview

pyST is a translator of a program written the the Structured Text (ST) language into a python program that tries to emulate its functional behavior.   The sole purpose of this translator is to create a tool for students to use when integrating logic expressed in ST (e.g. for a PLC controller) to create a form that is more amenable to integration with other software, and interactive debugging. In its present state pyST is very rudimentary, both in its approach to translation and in the subset of ST that is actually recognized.

This repository also contains what is needed to build and run a Docker container for an application that checks the syntax of ST programs.   The executable that performs the heavy lifting for this task was obtained from https://github.com/jubnzv/iec-checker and we are very grateful for the effort that went into this and the pre-built Linux application that performs the check.

This repository contains files in different categories

###### Syntax checking

- iec_checker_Linux_x86_64 , the Linux executable that performs the ST syntax checking
- Dockerfile , used to build a container that runs the executable of iec_checker_Linux_x86_64
- run_iec_check.sh , a shell script that calls Docker with the right flags for performing the analysis

###### ST to python translation

- pyST.py , the script run to transform an .st program into an 'equivalent' python program
- aux.py , python code that is copied into the python produced by pyST.py to provide support functions

###### Support for Modbus

- mbd.py , python file with data and methods used by the python translation of the .st file when interacting with Modbus.
- mbaux.py , python file with data and methods used by the python translation of the .st file when interacting with Modbus.
- mbstruct.py , python file with data and methods used by the python translation of the .st file when interacting with Modbus.

###### Example

- mbs.py ,  python file with three threads.  One thread provides a digital twin of an elevator system, another thread executes code presumably converted by pyST.py to create a PLC representation in python, the third is a Modbus server.
- args , a command line included when running mbs.py ,
- dt.py , python file with data and methods creating a digital twin of an elevator that is controlled by the PLC
- plc.py , python file presumeably created by pyST.py from a .st program designed to control the elevator
- plc.st , the originating ST program
- plc.json , file created by running pyST.py on plc.st that gives the mapping of variables to their locations in the interface shared with a device and in Modbus tables.
- mbc.py , file holding a Modbus client that interacts with the server in mbs.py to monitor what the PLC sees in the elevator.

### Useage

We go now through the various scripts and describe how to run them and (to a limited extent) how they work.

##### pyST.py

There are rigorous ways to translate an ST program into something else, and pyST.py isn't one of them.  A rigorous way would used compiler tools to parse the ST and turn it into a data structure that can be analyzed and have complete and proper translation techniques applied.  pyST.py was inspired by my discovery of a tool [ST2Py](#https://github.com/Destination2Unknown/ST2py) that avoided full up parsing of ST and relied instead on regular expression matching looking to transform well structured IF-THEN-ELSE blocks, FOR loops, etc, into Python equivalents.    I found though that ST2Py wasn't developed far enough to capture some features of ST programs that I want to accommodate, but the idea of using regular expressions and string matching was for me a viable path for a project that needed to come together quickly.

There are many many limitations on ST code that pyST needs to work.  It is not presently parsing declaration of user defined function blocks.   It recognizes the names of some function blocks (like TON) but does not yet have python implementations for any standard ones, although it does have implementations for a couple that we included for communication with Modbus.  Most particularly, pyST isn't yet trying to support timers that can be introduced by ST. There are many different distinctions of variable declaration types (e.g., VAR, INPUT_VAR, OUTPUT_VAR, etc.) but pyST.py works properly only if there is one VAR-END_VAR block naming variables visible to a single ST program.

We'll look at pieces of a transformation of the plc.st program we use in the example, given in its entirety below (with line numbers for easy reference.) 

```
  1 PROGRAM plc0
  2   VAR
  3     sys_state AT %IX0.0 : BOOL := TRUE;
  4     floor_req AT %IX0.1 : ARRAY[0..3] OF BOOL := [FALSE, FALSE, FALSE, FALSE];
  5     door_closed AT %IX0.5 : BOOL := TRUE;
  6     moving_up AT %IX0.6 : BOOL := FALSE;
  7     moving_down AT %IX0.7 : BOOL := FALSE;
  8 
  9     floor_level AT %IW0 : INT := 0;
 10 
 11     sys_on AT %QX0.0 : BOOL := TRUE;
 12     open_cmd  AT %QX0.1 : BOOL := FALSE;
 13     close_cmd AT %QX0.2 : BOOL := FALSE;
 14     move_up_cmd AT %QX0.3 : BOOL   := FALSE;
 15     move_down_cmd AT %QX0.4 : BOOL := FALSE;
 16 
 17     logic_state AT %MW0 : INT := 0;
 18     target_flr AT %MW1 : INT := 0;
 19     target_level AT %MW2 : INT := 0;
 20     selections AT %MW3 : INT := 0;
 21     current_flr AT %MW4 : INT := 0;
 22     count_down AT %MW5 : INT := 0;
 23 
 24     mb_import : IMPORT_FROM_MB;
 25     mb_export : EXPORT_TO_MB;
 26   END_VAR
```

Lines 2 through 26 describe the full set of variables.  Note that assignment to memory locations is uniformly present (and pyST requires this),  and that single dimensionally arrays can be declared.  All the variables shown here are initialized, but this is not a rigorous requirement by pyST .  Lines 24 and 25 show the declaration of two non-standard function blocks that we have defined.   There is no explicit representation of these in ST, rather, the translation turns these into python statements.

pyST translates this block of variable declarations into definition of variables at global scale:

```
429 sys_state = True
430 floor_req = [False, False, False, False]
431 door_closed = True
432 moving_up = False
433 moving_down = False
434 floor_level = 0
435 sys_on = True
436 open_cmd = False
437 close_cmd = False
438 move_up_cmd = False
439 move_down_cmd = False
440 logic_state = 0
441 target_flr = 0
442 target_level = 0
443 selections = 0
444 current_flr = 0
445 count_down = 0
446 mb_import = IMPORT_FROM_MB()
447 mb_export = EXPORT_TO_MB()
```

Here we notice that the declaration of function blocks are turned into constructor calls for python classes whose names are the function block type.  The line numbers in the file of transformed code reflects the copying of auxiliary support code (for all translations) contained in file aux.py .

Heading back to the .st file, a block of statements following the variable declaration is where the main loop of the code body starts:

```
 28   mb_import(TABLE="COIL", IDX=0, VALUE=>sys_on);
 29 
 30   CASE logic_state OF
 31     0:  // see if there any selections above present
 32         target_flr := -1;
 33 
 34         // loop up
 35         IF current_flr < 3 THEN
 36             FOR IDX:=current_flr+1 TO 3 DO
 37                 IF floor_req[IDX] = TRUE THEN
 38                     target_flr := IDX
 39                     EXIT;
 40                 END_IF;
 41             END_FOR;
 42         END_IF;
 43 
 44         // look down
 45         IF target_flr = -1 and current_flr > 0 THEN
 46             FOR IDX:=0 TO current_flr-1 DO
 47                 IF floor_req[IDX] = TRUE THEN
 48                     target_flr := IDX
 49                 END_IF;
 50             END_FOR;
 51         END_IF;
 52 
 53         // if target_flr is not -1 we select the target level
 54         // and apply power and change the logic_state
 55         IF target_flr <> -1 THEN
 56             IF target_flr < current_flr THEN
 57                 target_level := 4*target_flr + 1;
 58                 move_down_cmd := TRUE;
 59                 move_up_cmd := FALSE;
 60             ELSE
 61                 target_level := 4*target_flr -1;
 62                 move_up_cmd := TRUE;
 63                 move_down_cmd := FALSE;
 64             END_IF;
 65 
 66             logic_state := 1;
 67         END_IF;

```

The first line of the code body is a call to the function block that reads in information from the Modbus server. That call names the Modbus data table "COIL" as the one to be read (an appallation that we the user defined),  the index IDX in the table to read,  and that a function block output variable VALUE is to be applied to variable sys_on, which we earlier declared to be a Boolean program variable.  The next statement of the loop body is a CASE statement that implements a finite state machine for the PLC logic.  Without going into details, the roles of each state are

- 0 :  Scan the input interface with the digital twin for signals that indicate it has chosen another floor to visit. Stay in state 0 until that indication is observed, and write the to ST variable bound to the QX interface to command movement.  Also compute the floor level which, when the PLC observes the elevator has reached it, the PLC will clear that variable. After these actions ransition to state 1.
- 1 : Loiter in state 1 until observing that the elevator has recognized the command to move, by virtue of the variable bound to the X state bit it presents indicating movement.  Upon seeing recognized movement, transition to state 2:
- 2 : Loiter in state 2 until observing that the floor level of the elevator has reached the spot where the PLC will now drop the power to move, and then transition to state 3. 
- 3: The lowering of the command to move will be recognized by the elevator digital twin as it reaches the floor it was targeting, and at the end of that time-step it will report to the hardware interface state bits indicating that it is not presently moving.   The PLC loiters in state 3 until it observed that variables bound to those state bits are now low.  At this point it writes True to the variable bound to the QX bit signalling that the elevator door should be opened, and transitions to state 4.
- 4 : Loiter in state 4 until the variable bound to the state bit from the elevator reflecting the status of the door indicates that the command to open was recognized and executed.  On seeing this the PLC clears the 'open door command' initializes a count-down sequence where, once the sequence has completed, it will command the door to close, and transitions to state 5.
- 5 :  With every cycle through the PLC loop body, when in state 5 decrement the counter.  When it reaches 0 set the variable to communicate that the door should close, and transition to state 6.
- 6 : Loiter in state 6 until the variable bound to the IX bit indicating that the door is closed goes high, and then transition to state 0.

On one pass through the PLC loop body the import from Modbus is executed, then which ever of the case statements indicated by the state variable is executed, and then a sequence of calls to a function block that writes selected information out to the Modbus server:

```
109     6: // await evidence that the door has closed
110         IF door_closed = TRUE THEN
111             logic_state := 0;
112             close_cmd := FALSE;
113         END_IF;
114     END_CASE;
115 
116   mb_export(TABLE="DATA", IDX=0, VALUE := sys_state);
117   mb_export(TABLE="DATA", IDX=1, VALUE := moving_up or moving_down);
118   mb_export(TABLE="INPUT_REG", IDX=0, VALUE := logic_state);
119   mb_export(TABLE="INPUT_REG", IDX=1, VALUE := floor_level);
120   mb_export(TABLE="INPUT_REG", IDX=2, VALUE := target_level);
121 
122 END_PROGRAM

```

Lines 116-120 are all calls that cause the values indicated in the arguments to be exported to the indicated Modbus tables at the indicated indices.

What we *don't* see explicitly in the ST is the bit of magic that causes new values from the digital twin to appear in the ST variables, or vice versa.   Making that happen is a detail left to the PLC manufacturer, who I guess in this case is me.  So it is helpful perhaps to see what pyST.py does with this loop.

In preparation for entering the main PLC body loop, pyST embeds a string created as part of the transition process to describe all variables and their bindings to ST memory locations and Modbus table locations.  It then embeds in the code a call that transforms that string into a python dictionary.   These calls are shown below, admittedly dense.  Line 448 is the string-encoded json (a list of dictionaries), and line 449 creates a dictionary from these.

```
448 loc_map_str = '[{"name": "sys_state", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.0", "pos": 0, "value": "True", "mb_idx": 0}, {"na    me": "floor_req[0]", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.1", "pos": 1, "value": "True", "mb_idx": 1}, {"name": "floor_req[1    ]", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.2", "pos": 2, "value": "True", "mb_idx": 2}, {"name": "floor_req[2]", "var_type": "    BOOL", "py_type": "bool", "mem_code": "IX0.3", "pos": 3, "value": "True", "mb_idx": 3}, {"name": "floor_req[3]", "var_type": "BOOL", "py_type":     "bool", "mem_code": "IX0.4", "pos": 4, "value": "True", "mb_idx": 4}, {"name": "door_closed", "var_type": "BOOL", "py_type": "bool", "mem_code    ": "IX0.5", "pos": 5, "value": "True", "mb_idx": 5}, {"name": "moving_up", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.6", "pos": 6    , "value": "False", "mb_idx": 6}, {"name": "moving_down", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.7", "pos": 7, "value": "False    ", "mb_idx": 7}, {"name": "sys_on", "var_type": "BOOL", "py_type": "bool", "mem_code": "QX0.0", "pos": 0, "value": "True", "mb_idx": 0}, {"name    ": "open_cmd", "var_type": "BOOL", "py_type": "bool", "mem_code": "QX0.1", "pos": 1, "value": "False", "mb_idx": 1}, {"name": "close_cmd", "var    _type": "BOOL", "py_type": "bool", "mem_code": "QX0.2", "pos": 2, "value": "False", "mb_idx": 2}, {"name": "move_up_cmd", "var_type": "BOOL", "    py_type": "bool", "mem_code": "QX0.3", "pos": 3, "value": "False", "mb_idx": 3}, {"name": "move_down_cmd", "var_type": "BOOL", "py_type": "bool    ", "mem_code": "QX0.4", "pos": 4, "value": "False", "mb_idx": 4}, {"name": "floor_level", "var_type": "INT", "py_type": "int", "mem_code": "IW0    ", "pos": 0, "value": 0, "mb_idx": 0}, {"name": "logic_state", "var_type": "INT", "py_type": "int", "mem_code": "MW0", "pos": 0, "value": 0, "m    b_idx": 0}, {"name": "target_flr", "var_type": "INT", "py_type": "int", "mem_code": "MW1", "pos": 1, "value": 0, "mb_idx": 1}, {"name": "target    _level", "var_type": "INT", "py_type": "int", "mem_code": "MW2", "pos": 2, "value": 0, "mb_idx": 2}, {"name": "selections", "var_type": "INT",     "py_type": "int", "mem_code": "MW3", "pos": 3, "value": 0, "mb_idx": 3}, {"name": "current_flr", "var_type": "INT", "py_type": "int", "mem_code    ": "MW4", "pos": 4, "value": 0, "mb_idx": 4}, {"name": "count_down", "var_type": "INT", "py_type": "int", "mem_code": "MW5", "pos": 5, "value":     0, "mb_idx": 5}]'
449 loc_map = json.loads(loc_map_str)
```

Then, the ST code at the top of the PLC loop body is transformed to

```
450 def plc_thread_function(spc):
451     global sys_state,floor_req,door_closed,moving_up,moving_down
452     global floor_level,sys_on,open_cmd,close_cmd,move_up_cmd
453     global move_down_cmd,logic_state,target_flr,target_level,selections
454     global current_flr,count_down,mb_import,mb_export
455     build_loc_map(loc_map)
456     while True:
457         time.sleep(spc/1000)
458         top_of_cycle_import()
459         mb_import.call(TABLE="COIL", IDX=0)
460         sys_on = mb_import.VALUE
461         match  logic_state:
462             case 0:
463                 target_flr = -1
464                 if current_flr < 3 :
465                     for IDX in range(current_flr+1, (3)+1):
466                         if floor_req[IDX] == True :
467                             target_flr = IDX
468                             break
```

What's notable here is that the body of the PLC is encapsulated in the python `function plc_thread_function`.  That function will be writing (and reading) from the global variables that represent the ST variables, and so 'global' statements are needed to ensure the proper scope is recognized by the transformed code.   Line 455 shows the insertion of a call to a function 'build_loc_map' to transform the json description of variables we saw earlier into data structures used in the transition of data through the simulated hardware interface and the Modbus server.

Obviously the loop body is the body of the 'while True' loop, and what follows at the top is of some interest.  The sleep call suspends the loop for some period of time, and the first statement upon awakening is to call a route 'top_of_cycle_import()'.  This is a routine that is copied out of aux.py and placed in the main body of the pyST.py output script.  It uses the data structures created by the 'build_loc_map' call to copy the values in the IX and IW tables into the global python variables that are bound to them.  This is the software equivalent of reading values off a hardware interface and assiging them to program variables.  Another point of interest is the transformation of the call to function block 'mb_import.'  The one line in ST 

```
28   mb_import(TABLE="COIL", IDX=0, VALUE=>sys_on);
```

turns into two lines

```
459         mb_import.call(TABLE="COIL", IDX=0)
460         sys_on = mb_import.VALUE
```

where we see that execution of the function block is accomplished by calling the representative class method 'run', and that the ST code signaled by operator '=>' is turned into a variable assignment that references a field in the class instance.

The PLC main loop needs to copy its QX and QW bound variables to the data structures that represent the interface (and can be read by the digital twin). Looking at the bottom of the transformed loop we see explicit transformation of the calls to function block 'mb_export', and a call to a routine 'bottom_of_cycle_export' carried in from aux.py that exports the values of variables bound to the QX and QW memory locations to the data structures that represent QX and QW.

```
510             case 6:
511                 if door_closed == True :
512                     logic_state = 0
513                     close_cmd = False
514         mb_export.call(TABLE="DATA", IDX=0, VALUE = sys_state)
515         mb_export.call(TABLE="DATA", IDX=1, VALUE = moving_up or moving_down)
516         mb_export.call(TABLE="INPUT_REG", IDX=0, VALUE = logic_state)
517         mb_export.call(TABLE="INPUT_REG", IDX=1, VALUE = floor_level)
518         mb_export.call(TABLE="INPUT_REG", IDX=2, VALUE = target_level)
519         bottom_of_cycle_export()

```


I encourage users to check the syntax of .st programs they aim to transform, this is why I've provided the syntax checker.   There are however, seemingly some limitations of this program.

When applied to plc.st we observe

```
$ ./run_iec_check.sh plc.st
4:31 ParserError: 
```

That is indeed terse, and is indicating that it has a problem with line 4:

```
  4     floor_req AT %IX0.1 : ARRAY[0..3] OF BOOL := [FALSE, FALSE, FALSE, FALSE];
```

With some experimenting we discover that what it objects to is the inclusion of 'AT %IX0.1', for, by just removing it and applying the checker again we get

```
25:13 UnusedVariable: Found unused local variable: MB_EXPORT
24:13 UnusedVariable: Found unused local variable: MB_IMPORT
20:14 UnusedVariable: Found unused local variable: SELECTIONS
35:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
37:18 PLCOPEN-L17: Each IF instruction should have an ELSE clause
45:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
47:18 PLCOPEN-L17: Each IF instruction should have an ELSE clause
55:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
70:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
74:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
79:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
87:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
94:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
103:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
110:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
39:24 PLCOPEN-L10: Usage of CONTINUE and EXIT instruction should be avoid
0:0 PLCOPEN-CP9: Code is too complex (90 statements)
0:0 PLCOPEN-CP9: Code is too complex (101 McCabe complexity)
22:14 PLCOPEN-CP4: Address of direct variable %WM5 (size 2) should not overlap with direct variable %WM4
21:15 PLCOPEN-CP4: Address of direct variable %WM4 (size 2) should not overlap with direct variable %WM5
20:14 PLCOPEN-CP4: Address of direct variable %WM3 (size 2) should not overlap with direct variable %WM4
19:16 PLCOPEN-CP4: Address of direct variable %WM2 (size 2) should not overlap with direct variable %WM3
18:14 PLCOPEN-CP4: Address of direct variable %WM1 (size 2) should not overlap with direct variable %WM2
17:15 PLCOPEN-CP4: Address of direct variable %WM0 (size 2) should not overlap with direct variable %WM1
9:15 PLCOPEN-CP4: Address of direct variable %WI0 (size 2) should not overlap with direct variable %WM1
25:13 PLCOPEN-CP3: Variable MB_EXPORT shall be initialized before being used
24:13 PLCOPEN-CP3: Variable MB_IMPORT shall be initialized before being used
```

Going through these carefully, the first two indicate that our trick of not explicitly creating function block representation for our Modbus interface blocks is not appreciated by the checker.   The third complaint of not using variable 'selections' declared on line 11 is indeed valid.  The lines asserting that every IF statement should have an ELSE is not a language requirement,  as is the warning not to use CONTINUE or EXIT.   The warnings citing PLCOPEN-CP4 seem to be at odds with explanations and examples in whether the index value associated with WM is an index number (since the size of each element of WM is known) or a byte address.   Our implementation of the data tables assumes the indexing interpretation and so we ignore all those warnings.  The last two warnings are like the first two, explanable by our slight-of-hand to be conducted when executing these function blocks.

We put the assignment of floor_req back into the ST file, not only because we don't have another mechanism to assign it to an memory class, but also because we have seen instances where arrays were indeed initialized this way.   As with many things it seems with ST implementation, it comes down to the selection of the manufacturer.

##### dt.py

The elevator digital twin in this example is simpler than the one done for a class project.  Each floor has only one request button.  When it comes to chose another floor, the digital twin randomly choses one randomly.

The digital twin executes in a loop where at the top of the loop it sleeps for a period, and upon awakening updates its position if it has been in motion.   Following this it reads in the values presented to it in the QX table that represents its hardware interface with the PLC.

The commands to the digital twin (QX table) are

- QX0.0  System 'on' button.  Must be high for the elevator to operate.
- QX0.1  Open door command. Once seen and executed does not have to be held open for the door to stay open. Must be observed explicitly to cause the door to open.
- QX0.2  Close door command.  Once seen and executed does not have to be held open for the door to stay closed.  Must be observed explicitly to cause the door to close.
- QX0.3  Move up command.  When high the elevator is put in motion going up.  When dropped, the upward motion stops.
- QX0.4  Move down command.  When high the elevator is put in motion going down.  When dropped the downward motion stops.

On processing its commands it updates its state and at the end of the time-step writes out state information to the IX table that is read by the PLC.  These are

- IX0.0  System state (on or off)
- IX0.1 Request for floor 0
- IX0.2 Request for floor 1
- IX0.3 Request for floor 2
- IX0.4 Request for floor 3
- IX0.5 Door is closed
- IX0.6  Elevator is moving up
- IX0.7 Elevator is moving down
- IW0  Current elevator position

The actions of the elevator are pretty much just following the commands that arrive through the QX table.   In a time-step where the elevator responds to a command to open the door, it also clears the request to arrive at the floor where it has presently stopped, and randomly choses another floor and raises the corresponding IX line to signal that.

##### mbs.py

The mbs.py file runs three threads.   One handles the digital twin, one handles the PLC, and the last handles the Modbus server.  At a high level, what one does is to start mbs.py, whereupon the PLC awaits a signal via Modbus to start the system and the digital twin awaits a signal through the QX interface that the system is running before it recognizes any other commands.  The essential command line statements are in file args

```
-cport 5020
-mpc 100
-seed 45623
```

Where -cport names the port used to communicate with the Modbus server, -mpc gives the number of milliseconds to elapse in the PLC each cycle (and from which the number of milliseconds per time-stamp is computed for the digital twin, to be x5 larger), and -seed gives a random number seed which we include to ensure deterministic behavior when we are debugging.

To start the server, we execute the command below, and see the report that the server is waiting for a connection.

```
$ python mbs.py -is args 
listening for client on (127.0.0.1, 5020)
```

##### mbc.py

In this example the Modbus client does very little; it exists here mostly to demonstrate the functionality the system and example. The initialization of the PLC thread is done so that it requires a Modbus client to signal the system on.   So our mbc.py example waits 5 seconds after being started, and then raises the 'on_sys' coil for the PLC.   Following this, the client enters a loop where it sleeps for two seconds, and upon awakening queries the Modbus server for the state values that the PLC writes to the Modbus server at the end of every cycle.  There are five of these:

- sys_state , True when the system is running
- moving ,  True when the elevator is in motion
- state idx in the PLC's state machine
- current floor level of the elevator as seen by the PLC
- target floor level when the elevator is in motion which, when reached, will cause the PLC to drop the power coils and stop the elevator motion at the next time-step (where it will have just advanced to the target floor).

Running mbc.py is as simple as seen below

```
$ python mbc.py -port 5020
open socket to 127.0.0.1:5020
```

It reports that it has opened a socket. Until the mbs server (or some other Modbus ported app) hangs out a 5020 shingle nothing will happen.

##### Running Example

So now will stand everything up and give screen grabs of what the processes report.  We include line numbers here for reference.

```
  1 $ python mbs.py -is args                               
  2 listening for client on (127.0.0.1, 5020)
  3 start moving up from position 0
  4 power stopped at position 8
  5 door opens at position 8
  6 door requests [False, False, False, True]
  7 door closes at position 8
  8 start moving up from position 8
  9 power stopped at position 12
 10 door opens at position 12
 11 door requests [True, False, False, False]
 12 door closes at position 12
 13 start moving down from position 12
 14 power stopped at position 0
 15 door opens at position 0
 16 door requests [False, False, True, False]
 17 door closes at position 0
 18 start moving up from position 0
 19 power stopped at position 8
 20 door opens at position 8
 21 door requests [False, True, False, False]
```

​									Trace from Digital Twin





```
  1 $ python mbc.py -port 5020
  2 open socket to 127.0.0.1:5020
  3 connected to 127.0.0.1:5020
  4 sys_on True, moving True
  5 srv_state 2, floor level 2, target level 7
  6 
  7 sys_on True, moving True
  8 srv_state 2, floor level 6, target level 7
  9 
 10 sys_on True, moving False
 11 srv_state 5, floor level 8, target level 7
 12 
 13 sys_on True, moving True
 14 srv_state 2, floor level 9, target level 11
 15 
 16 sys_on True, moving False
 17 srv_state 5, floor level 12, target level 11
 18 
 19 sys_on True, moving True
 20 srv_state 2, floor level 12, target level 1
 21 
 22 sys_on True, moving True
 23 srv_state 2, floor level 8, target level 1
 24 
 25 sys_on True, moving True
 26 srv_state 2, floor level 4, target level 1
 27 
 28 sys_on True, moving False
 29 srv_state 4, floor level 0, target level 1

```

​								Trace from Modbus Client

We see from the digital twin trace that the first target floor after the system starts (lines 3-5) is at level 8 (floor 2), which it reaches and recognizes a command to open the door.    The Modbus client prints two lines at the end of each of its probe cycles, with a carriage return between. The first report (lines 4-5) are that the elevator is observed to be in motion, moving up, aiming to drop the power coil when the elevator hits stage 7, which will mean the elevator stops on reaching stage 8, which is floor 2, which is consistent with the observations from the digital twin trace.  Lines 10-11 on the client trace show the elevator stopped at stage 8, next seen moving up towards level 12 (floor 3), which the client sees has been reached and the elevator stopped by the observations at lines 16-17.    Looking at the digital twin trace lines 6-9 we see that floor 4 was selected, that the elevator reaches that floor, stops, and opens the door.

Thus we see that from digital twin to PLC to Modbus client the information and control flows appear to be working as designed.



