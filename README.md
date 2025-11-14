



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
 18     target_flr_code AT %MW1 : INT := 0;
 19     obs_target_flr_code AT %MW2 : INT := 0;
 20     target_flr AT %MW3 : INT := 0;
 21     target_level AT %MW4 : INT := 0;
 22     current_flr AT %MW5 : INT := 0;
 23     count_down AT %MW6 : INT := 0;
 24 
 25     ms_per_cycle AT %MW7 : INT := 100;
 26 
 27     mb_import : IMPORT_FROM_MB;
 28     mb_export : EXPORT_TO_MB;
 29   END_VAR
```

Lines 2 through 28 describe the full set of variables.  Note that assignment to memory locations is uniformly present (and pyST requires this),  and that single dimensional  arrays can be declared.  All the variables shown here are initialized, but this is not a rigorous requirement by pyST .  Lines 27 and 28 show the declaration of two non-standard function blocks that we have defined.   There is no explicit representation of these in ST, rather, the translation turns these into python statements.

pyST translates this block of variable declarations into definition of variables at global scale:

```
435 sys_state = True
436 floor_req = [False, False, False, False]
437 door_closed = True
438 moving_up = False
439 moving_down = False
440 floor_level = 0
441 sys_on = True
442 open_cmd = False
443 close_cmd = False
444 move_up_cmd = False
445 move_down_cmd = False
446 logic_state = 0
447 target_flr_code = 0
448 obs_target_flr_code = 0
449 target_flr = 0
450 target_level = 0
451 current_flr = 0
452 count_down = 0
453 ms_per_cycle = 100
454 mb_import = IMPORT_FROM_MB()
455 mb_export = EXPORT_TO_MB()
```

Here we notice that the declaration of function blocks are turned into constructor calls for python classes whose names are the function block type.  The line numbers in the file of transformed code reflects the copying of auxiliary support code (for all translations) contained in file aux.py .

Heading back to the .st file, a block of statements following the variable declaration is where the main loop of the code body starts:

```
 31   // is the system 'on'
 32   mb_import(TABLE="COIL", IDX=0, LEN=1, VALUE=>sys_on);
 33 
 34   // the target_flr_code is non-zero when the controller has selected 
 35   // a floor and written its identity (plus 1) into the target_flr_code variable
 36   // 
 37   mb_import(TABLE="HOLDING_REG", IDX=0, LEN=1, VALUE=>obs_target_flr_code);
 38  
 39   IF obs_target_flr_code <> target_flr_code THEN
 40        target_flr_code := obs_target_flr_code;
 41   END_IF;
 42 
 43   CASE logic_state OF
 44     0:  // wait for client to select target floor
 45         IF target_flr_code > 0 THEN
 46             // floor is chosen so we compute the target level,
 47             // apply power, and change the logic_state
 48             //
 49             target_flr := target_flr_code-1;
 50             IF target_flr < current_flr THEN
 51                 target_level := 4*target_flr + 1;
 52                 move_down_cmd := TRUE;
 53                 move_up_cmd := FALSE;
 54             ELSE
 55                 target_level := 4*target_flr -1;
 56                 move_up_cmd := TRUE;
 57                 move_down_cmd := FALSE;
 58             END_IF;
 59             target_flr_code := 0;
 60             logic_state := 1;
 61         END_IF;
 62   
```

The first line of the code body is a call to the function block that reads in information from the Modbus server. That call names the Modbus data table "COIL" as the one to be read (an appallation that we the user defined),  the index IDX in the table to read,  and that a function block output variable VALUE is to be applied to variable sys_on, which we earlier declared to be a Boolean program variable.  The next statement is another call to mb_import, this time to read the integer in the holding_register index 0,  which is a code that a Modbus client uses to indicate which next floor the controller ought to cause the elevator to move to.  We want to be able to distinguish between some specific request and no request, and so have adopted the strategy of using 0 to indicate there is no request, and the requested floor plus 1 to encode a request for a specific floor.  Lines 39-41 are assigning the read-in floor code to a variable 'target_flr_code' for the purposes of remembering the request across multiple execution loops of the PLC code body.

Line 43 starts a CASE statement that implements a finite state machine for the PLC logic.  Without going into details, the roles of each state are

- 0 :  Wait for the Modbus client to select a floor. When chosen compute the floor level where the move command will be dropped, and assign movement commands to the interface variables the digital twin will monitor to determine what movement to make.
- 1 : Loiter in state 1 until observing that the elevator has recognized the command to move, by virtue of the variable bound to the X state bit it presents indicating movement.  Upon seeing recognized movement, transition to state 2:
- 2 : Loiter in state 2 until observing that the floor level of the elevator has reached the spot where the PLC will now drop the power to move, and then transition to state 3. 
- 3: The lowering of the command to move will be recognized by the elevator digital twin as it reaches the floor it was targeting, and at the end of that time-step it will report to the hardware interface state bits indicating that it is not presently moving.   The PLC loiters in state 3 until it observed that variables bound to those state bits are now low.  At this point it writes True to the variable bound to the QX bit signalling that the elevator door should be opened, and transitions to state 4.
- 4 : Loiter in state 4 until the variable bound to the state bit from the elevator reflecting the status of the door indicates that the command to open was recognized and executed.  On seeing this the PLC clears the 'open door command' initializes a count-down sequence where, once the sequence has completed, it will command the door to close, and transitions to state 5.
- 5 :  With every cycle through the PLC loop body, when in state 5 decrement the counter.  When it reaches 0 set the variable to communicate that the door should close, and transition to state 6.
- 6 : Loiter in state 6 until the variable bound to the IX bit indicating that the door is closed goes high, and then transition to state 0.

On one pass through the PLC loop body the import from Modbus is executed, then which ever of the case statements indicated by the state variable is executed, and then a sequence of calls to a function block that writes selected information out to the Modbus server:

```
103     6: // await evidence that the door has closed
104         IF door_closed = TRUE THEN
105             logic_state := 0;
106             close_cmd := FALSE;
107         END_IF;
108     END_CASE;
109 
110   // report whether on or off
111   mb_export(TABLE="DATA", IDX=0, VALUE := sys_state);
112 
113   // report whether door is closed
114   mb_export(TABLE="DATA", IDX=1, VALUE := door_closed);
115 
116   // report whether in motion
117   mb_export(TABLE="DATA", IDX=2, VALUE := moving_up or moving_down);
118  
119   // if the elevator is not moving, the floor is where the elevator car rests
120   mb_export(TABLE="INPUT_REG", IDX=0, VALUE := current_flr);
121 
122   // the count_down is the number of milliseconds until the door closes
123   mb_export(TABLE="INPUT_REG", IDX=1, VALUE := count_down*ms_per_cycle);
124 
125   // export the table of floor requests, to inform the client of requests
126   mb_export(TABLE="INPUT_REG", IDX=2, VALUE := floor_req, START=0, LEN=4);
127 
128   // export the communicated target floor code, as an ACK to the client
129   mb_export(TABLE="HOLDING_REG", IDX=0, VALUE := obs_target_flr_code);
130 
131 END_PROGRAM
```

Lines 111-129 are all calls that cause the values indicated in the arguments to be exported to the indicated Modbus tables at the indicated indices.

What we *don't* see explicitly in the ST is the bit of magic that causes new values from the digital twin to appear in the ST variables, or vice versa.   Making that happen is a detail left to the PLC manufacturer, who I guess in this case is me.  So it is helpful perhaps to see what pyST.py does with this loop.

In preparation for entering the main PLC body loop, pyST embeds a string created as part of the transition process to describe all variables and their bindings to ST memory locations and Modbus table locations.  It then embeds in the code a call that transforms that string into a python dictionary.   These calls are shown below, admittedly dense.  Line 448 is the string-encoded json (a list of dictionaries), and line 449 creates a dictionary from these.

```
456 loc_map_str = '[{"name": "sys_state", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.0", "pos": 0, "value": "True", "mb_idx": 0}, {"na    me": "floor_req[0]", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.1", "pos": 1, "value": "True", "mb_idx": 1}, {"name": "floor_req[1    ]", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.2", "pos": 2, "value": "True", "mb_idx": 2}, {"name": "floor_req[2]", "var_type": "    BOOL", "py_type": "bool", "mem_code": "IX0.3", "pos": 3, "value": "True", "mb_idx": 3}, {"name": "floor_req[3]", "var_type": "BOOL", "py_type":     "bool", "mem_code": "IX0.4", "pos": 4, "value": "True", "mb_idx": 4}, {"name": "door_closed", "var_type": "BOOL", "py_type": "bool", "mem_code    ": "IX0.5", "pos": 5, "value": "True", "mb_idx": 5}, {"name": "moving_up", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.6", "pos": 6    , "value": "False", "mb_idx": 6}, {"name": "moving_down", "var_type": "BOOL", "py_type": "bool", "mem_code": "IX0.7", "pos": 7, "value": "False    ", "mb_idx": 7}, {"name": "sys_on", "var_type": "BOOL", "py_type": "bool", "mem_code": "QX0.0", "pos": 0, "value": "True", "mb_idx": 0}, {"name    ": "open_cmd", "var_type": "BOOL", "py_type": "bool", "mem_code": "QX0.1", "pos": 1, "value": "False", "mb_idx": 1}, {"name": "close_cmd", "var    _type": "BOOL", "py_type": "bool", "mem_code": "QX0.2", "pos": 2, "value": "False", "mb_idx": 2}, {"name": "move_up_cmd", "var_type": "BOOL", "    py_type": "bool", "mem_code": "QX0.3", "pos": 3, "value": "False", "mb_idx": 3}, {"name": "move_down_cmd", "var_type": "BOOL", "py_type": "bool    ", "mem_code": "QX0.4", "pos": 4, "value": "False", "mb_idx": 4}, {"name": "floor_level", "var_type": "INT", "py_type": "int", "mem_code": "IW0    ", "pos": 0, "value": 0, "mb_idx": 0}, {"name": "logic_state", "var_type": "INT", "py_type": "int", "mem_code": "MW0", "pos": 0, "value": 0, "m    b_idx": 0}, {"name": "target_flr_code", "var_type": "INT", "py_type": "int", "mem_code": "MW1", "pos": 1, "value": 0, "mb_idx": 1}, {"name": "o    bs_target_flr_code", "var_type": "INT", "py_type": "int", "mem_code": "MW2", "pos": 2, "value": 0, "mb_idx": 2}, {"name": "target_flr", "var_ty    pe": "INT", "py_type": "int", "mem_code": "MW3", "pos": 3, "value": 0, "mb_idx": 3}, {"name": "target_level", "var_type": "INT", "py_type": "in    t", "mem_code": "MW4", "pos": 4, "value": 0, "mb_idx": 4}, {"name": "current_flr", "var_type": "INT", "py_type": "int", "mem_code": "MW5", "pos    ": 5, "value": 0, "mb_idx": 5}, {"name": "count_down", "var_type": "INT", "py_type": "int", "mem_code": "MW6", "pos": 6, "value": 0, "mb_idx":     6}, {"name": "ms_per_cycle", "var_type": "INT", "py_type": "int", "mem_code": "MW7", "pos": 7, "value": 100, "mb_idx": 7}]'
457 loc_map = json.loads(loc_map_str)
```

Then, the ST code at the top of the PLC loop body is transformed to

```
458 def plc_thread_function(spc):
459     global sys_state,floor_req,door_closed,moving_up,moving_down
460     global floor_level,sys_on,open_cmd,close_cmd,move_up_cmd
461     global move_down_cmd,logic_state,target_flr_code,obs_target_flr_code,target_flr
462     global target_level,current_flr,count_down,ms_per_cycle,mb_import
463     global mb_export
464     build_loc_map(loc_map)
465     while True:
466         time.sleep(spc/1000)
467         top_of_cycle_import()
468         # is the system 'on'
469         mb_import.call(TABLE="COIL", IDX=0, LEN=1)
470         sys_on = mb_import.VALUE
471         # the target_flr_code is non-zero when the controller has selected
472         # a floor and written its identity (plus 1) into the target_flr_code variable
473         #
474         mb_import.call(TABLE="HOLDING_REG", IDX=0, LEN=1)
475         obs_target_flr_code = mb_import.VALUE
476         if obs_target_flr_code != target_flr_code :
477             target_flr_code = obs_target_flr_code
478         match  logic_state:
479             case 0:
480                 if target_flr_code > 0 :
481                     target_flr = target_flr_code-1
482                     if target_flr < current_flr :
483                         target_level = 4*target_flr + 1
484                         move_down_cmd = True
485                         move_up_cmd = False
486                     else:
487                         target_level = 4*target_flr -1
488                         move_up_cmd = True
489                         move_down_cmd = False
490                     target_flr_code = 0
491                     logic_state = 1

```

What's notable here is that the body of the PLC is encapsulated in the python `function plc_thread_function`.  That function will be writing (and reading) from the global variables that represent the ST variables, and so 'global' statements are needed to ensure the proper scope is recognized by the transformed code.   Line 464 shows the insertion of a call to a function 'build_loc_map' to transform the json description of variables we saw earlier into data structures used in the transition of data through the simulated hardware interface and the Modbus server.

Obviously the loop body is the body of the 'while True' loop, and what follows at the top is of some interest.  The sleep call suspends the loop for some period of time, and the first statement upon awakening is to call a route 'top_of_cycle_import()'.  This is a routine that is copied out of aux.py and placed in the main body of the pyST.py output script.  It uses the data structures created by the 'build_loc_map' call to copy the values in the IX and IW tables into the global python variables that are bound to them.  This is the software equivalent of reading values off a hardware interface and assiging them to program variables.  Another point of interest is the transformation of the call to function block 'mb_import.'  The one line in ST 

```
32   mb_import(TABLE="COIL", IDX=0, VALUE=>sys_on);
```

turns into two lines

```
469         mb_import.call(TABLE="COIL", IDX=0)
470         sys_on = mb_import.VALUE
```

where we see that execution of the function block is accomplished by calling the representative class method 'run', and that the ST code signaled by operator '=>' is turned into a variable assignment that references a field in the class instance.

The PLC main loop needs to copy its QX and QW bound variables to the data structures that represent the interface (and can be read by the digital twin). Looking at the bottom of the transformed loop we see explicit transformation of the calls to function block 'mb_export', and a call to a routine 'bottom_of_cycle_export' carried in from aux.py that exports the values of variables bound to the QX and QW memory locations to the data structures that represent QX and QW.

```
519             case 6:
520                 if door_closed == True :
521                     logic_state = 0
522                     close_cmd = False
523         # report whether on or off
524         mb_export.call(TABLE="DATA", IDX=0, VALUE = sys_state)
525         # report whether door is closed
526         mb_export.call(TABLE="DATA", IDX=1, VALUE = door_closed)
527         # report whether in motion
528         mb_export.call(TABLE="DATA", IDX=2, VALUE = moving_up or moving_down)
529         # if the elevator is not moving, the floor is where the elevator car rests
530         mb_export.call(TABLE="INPUT_REG", IDX=0, VALUE = current_flr)
531         # if the elevator is not moving, the count_down is the number of milliseconds until the door closes
532         mb_export.call(TABLE="INPUT_REG", IDX=1, VALUE = count_down*ms_per_cycle)
533         # export the table of floor requests
534         mb_export.call(TABLE="INPUT_REG", IDX=2, VALUE = floor_req, START=0, LEN=4)
535         # export the communicated target floor code so that client knows it has been received
536         mb_export.call(TABLE="HOLDING_REG", IDX=0, VALUE = obs_target_flr_code)
537         bottom_of_cycle_export()
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
28:13 UnusedVariable: Found unused local variable: MB_EXPORT
27:13 UnusedVariable: Found unused local variable: MB_IMPORT
39:4 PLCOPEN-L17: Each IF instruction should have an ELSE clause
45:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
64:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
68:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
73:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
81:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
88:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
97:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
104:10 PLCOPEN-L17: Each IF instruction should have an ELSE clause
0:0 PLCOPEN-CP9: Code is too complex (97 statements)
0:0 PLCOPEN-CP9: Code is too complex (97 McCabe complexity)
25:16 PLCOPEN-CP4: Address of direct variable %WM7 (size 2) should not overlap with direct variable %WM6
23:14 PLCOPEN-CP4: Address of direct variable %WM6 (size 2) should not overlap with direct variable %WM7
22:15 PLCOPEN-CP4: Address of direct variable %WM5 (size 2) should not overlap with direct variable %WM6
21:16 PLCOPEN-CP4: Address of direct variable %WM4 (size 2) should not overlap with direct variable %WM5
20:14 PLCOPEN-CP4: Address of direct variable %WM3 (size 2) should not overlap with direct variable %WM4
19:20 PLCOPEN-CP4: Address of direct variable %WM2 (size 2) should not overlap with direct variable %WM3
18:19 PLCOPEN-CP4: Address of direct variable %WM1 (size 2) should not overlap with direct variable %WM2
17:15 PLCOPEN-CP4: Address of direct variable %WM0 (size 2) should not overlap with direct variable %WM1
9:15 PLCOPEN-CP4: Address of direct variable %WI0 (size 2) should not overlap with direct variable %WM1
28:13 PLCOPEN-CP3: Variable MB_EXPORT shall be initialized before being used
27:13 PLCOPEN-CP3: Variable MB_IMPORT shall be initialized before being used
```

Going through these carefully, the first two indicate that our trick of not explicitly creating function block representation for our Modbus interface blocks is not appreciated by the checker.   The lines asserting that every IF statement should have an ELSE is not a language requirement,  as is the warning not to use CONTINUE or EXIT.   The warnings citing PLCOPEN-CP4 seem to be at odds with explanations and examples in whether the index value associated with WM is an index number (since the size of each element of WM is known) or a byte address.   Our implementation of the data tables assumes the indexing interpretation and so we ignore all those warnings.  The last two warnings are like the first two, explanable by our slight-of-hand to be conducted when executing these function blocks.

We put the assignment of floor_req back into the ST file, not only because we don't have another mechanism to assign it to an memory class, but also because we have seen instances where arrays were indeed initialized this way.   As with many things it seems with ST implementation, it comes down to the selection of the manufacturer.

##### dt.py

The elevator digital twin in this example is simpler than the one done for a class project.  Each floor has only one request selection.  When it comes to signal a request to visit another floor, the digital twin choses one randomly.

The digital twin executes in a loop where at the top of the loop it sleeps for a period, and upon awakening updates its position if it has been in motion.   Following this it reads in the values presented to it in the QX table that represent its hardware interface with the PLC.

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

The digital twin uses routines named `read_QX`, `read_QW` , `write_IX`, `write_IW` , and `write_MW` to transfer state values to the data structures in the PLC that represent the interface between the digital twin and the PLC.  The interpretation of what a function does is obvious from its name.

```
187 def read_QX(first, last):
188     OK, values = plc.QX_seq.read_values(first, last)
189     if not OK:
190         print(f"read_QX from {first} to {last} failed")
191         return []
192     return True, values
193 
194 def read_QW(first, last):
195     OK, values = plc.QW_seq.read_values(first, last)
196     if not OK:
197         print(f"read_QW from {first} to {last} failed")
198         return []
199     return True, values
200             
201 
202 def write_IX(first, last, values):
203     OK = plc.IX_seq.write_values(first, last, values)
204     if not OK:
205         print(f"write_IX from {first} to {last} failed")
206 
207 def write_IW(first, last, values):
208     OK = plc.IW_seq.write_values(first, last, values)
209     if not OK:
210         print(f"write_IW from {first} to {last} failed")
211 
212 def write_MW(first, last, values):
213     OK = plc.MW_seq.write_values(first, last, values)
214     if not OK:
215         print(f"write_MW from {first} to {last} failed")
```

These functions call methods associated with a `var_seq` class in the PLC code. These are the very data structures accessed by the calls `top_of_cycle_import` and `bottom_of_cycle_export` embedded by the ST to python translator to load ST program variables.

The actions of the elevator are pretty much just following the commands that arrive through the QX table.   In a time-step where the elevator responds to a command to open the door it randomly choses another floor another floor to visit and raises the corresponding IX line to signal that.  The logic of the digital twin has it choosing a floor when processing a time-step where the command to open the door is present while that command was not present in the previous time-step.  The digital twin clears all posted requests in a time-step when a command to power up or power down is recognized, while neither command was present in the previous time step.   Provided that the pause time per loop in the PLC is significantly less than the sleep time per time step in the digital twin, we can infer that the PLC loop executed at least once between the instance when the digital twin posted the visit request, and when power commands were recognized by the digital twin, meaning that the requests were captured by the PLC and it is safe for the digital twin to erase them.  Furthermore the PLC finite state machine waits after posting any command for evidence that the digital twin recognized it and acted on it.

So then the digital twin chooses 'the next' floor to visit and communicates that to the PLC through the IX tables.   The PLC program variables are load with these requests, and at the end of that pass of the control loop all these variables are written into Modbus data tables.  Some time later the Modbus client will read those input tables and notice that it needs to select the next floor from among all the known requests.  It does so, and using Modbus writes a code of the dentity of the chosen floor to the holding registers table.   Now at the top of every pass through the PLC control loop, the holding register to which that coded selection was written is read from the Modbus table, and passes where a selection is newly recognized take that selection and transform it so that the PLC can power the elevator in the proper direction, and drop the power at the proper time to see it glide to a halt at the selected floor.

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

In this example the Modbus client powers the system on, and chooses which floor the elevator next visits.   It is written so that five seconds elapse after the client is started (and a socket to the Modbus server on the PLC is created), after which raises the coil that signals the PLC that the system is on, and enters a loop that executes considerably less frequently than the PLC or digital twin loops.  At the top of the loop it waits for two seconds.   It then does Modbus reads of all the discrete inputs, input registers, and holding registers mapped to the Modbus data tables and enters the present state of a finite state machine which governs its further actions.    The values read in are

- (Discrete input) system is on.
- (Discrete input) the elevator door is closed.
- (Discrete input) the elevator is in motion.
- (Input register) The current floor at which a resting elevator resides.
- (Input register) Number of milliseconds until an open elevator door closes.
- (Input register) List of 4 booleans, for floors 0-3, indicating for each whether that floor has been chosen to visit.
- (Holding register) Code for selected floor to visit.

After one pass through the FSM it writes back to the holding register a code for the identity of the next floor for the elevator to visit.

The FSM has four states, and on the first pass enters state 0.

- State 0: Loiter in state 0 until the elevator door is closed and the elevator is not moving.   This means the elevator since the elevator computes another floor visit request in the time-step when the door opens, we are assured that the client has the vector of requests and the elevator is in a state where it can accept a new floor to visit.  Once this condition is met the FSM transitions to state 1.
- State 1: The vector of requests is analyzed and the floor closest to the current one is chosen, with a tie-breaker going to the lower floor.  A code for the selected floor is saved for communication to the Modbus server attached to the PLC at the end of the loop.  The FSM transitions to state 2.
- State 2:  The code for the selected floor was written out at the end of the loop where state 1 was executed, and so by the time control enters state 2 we are assured it has been communicated.  Control loiters in state 2 until receiving evidence that the selected next floor has been recognized by the PLC.   This recognition occurs by noting that the value read at the top of the loop from the holding register containing the floor selection exactly equals the value last written by the client into that register, for the PLC will simply echo what it receives back through Modbus.   The holding register is loaded with a code indicating that no floor directive is present, and the FSM transitions to state 3.
- State 3: Control loiters in state 3 until it sees that the elevator is not moving, and that the selection code for next floor read in at the top of the loop is equal to the 'no request present' code written out after passing out of state 2.



Running mbc.py is as simple as seen below

```
$ python mbc.py -port 5020
open socket to 127.0.0.1:5020
```

It reports that it has opened a socket. Until the mbs server (or some other Modbus ported app) hangs out a 5020 shingle nothing will happen.

##### Running Example

So now will stand everything up and give screen grabs of what the processes report.  We include line numbers here for reference.

```
  1 $ python mbs.py -cport 5020
  2 listening for client on (127.0.0.1, 5020)
  3 start moving up from floor 0
  4 power stopped at floor 3
  5 door opens at floor 3
  6 door closes at floor 3
  7 start moving down from floor 3
  8 power stopped at floor 0
  9 door opens at floor 0
 10 door closes at floor 0
 11 start moving up from floor 0
 12 power stopped at floor 1
 13 door opens at floor 1
 14 door closes at floor 1
 15 start moving up from floor 1
 16 power stopped at floor 2
 17 door opens at floor 2

```

​									Trace from Digital Twin

where we print out record of an event at they happen, while in the terminal where we run mbc.py print out state information at the top of the control loop.

```
$ python mbc.py -port 5020
  2 open socket to 127.0.0.1:5020
  3 connected to 127.0.0.1:5020
  4 mbc sys_state True, floor 0, door_closed True, moving False
  5     req_flr [0, 0, 0, 1]
  6 mbc sys_state True, floor 0, door_closed True, moving False
  7     req_flr [0, 0, 0, 1]
  8 choose next flr 3
  9 mbc sys_state True, floor 0, door_closed True, moving True
 10     req_flr [0, 0, 0, 0]
 11 mbc sys_state True, floor 0, door_closed True, moving True
 12     req_flr [0, 0, 0, 0]
 13 mbc sys_state True, floor 0, door_closed True, moving True
 14     req_flr [0, 0, 0, 0]
 15 mbc sys_state True, floor 3, door_closed False, moving False
 16     req_flr [1, 0, 0, 0]
 17 mbc sys_state True, floor 3, door_closed True, moving False
 18     req_flr [1, 0, 0, 0]
 19 mbc sys_state True, floor 3, door_closed True, moving False
 20     req_flr [1, 0, 0, 0]
 21 choose next flr 0
 22 mbc sys_state True, floor 3, door_closed True, moving True
 23     req_flr [0, 0, 0, 0]
 24 mbc sys_state True, floor 3, door_closed True, moving True
 25     req_flr [0, 0, 0, 0]
 26 mbc sys_state True, floor 3, door_closed True, moving True
 27     req_flr [0, 0, 0, 0]
 28 mbc sys_state True, floor 0, door_closed False, moving False
 29     req_flr [0, 1, 0, 0]
 30 mbc sys_state True, floor 0, door_closed True, moving False
 31     req_flr [0, 1, 0, 0]
 32 mbc sys_state True, floor 0, door_closed True, moving False
 33     req_flr [0, 1, 0, 0]
 34 choose next flr 1

```

​								Trace from Modbus Client

Lines 4-8 of the client trace show that the elevator is not in motion and has communicated a request to travel to floor 3 (the last '1' in the four element vector reporting the values of array 'req_flr'). Line 8 reports that the client chooses floor 3.  Lines 9-14 capture that the elevator recognized a command to move up, cleared its vector of requests.  Lines 15-16 reflect that the elevator is stopped at floor 3, has openned the door, and (as part of the logic associated with opening the door ) selected floor 0 as the next one to visit.  Looking now at the digital twin trace we in lines 3-5 that the elevator started moving up, stopped at floor 3, and openned its doors.  In lines 7-10 it reports descending to floor 0, then in lines 11-14 it reports ascending to floor 1.   We see this same pattern in the client trace, where lines 15-29 show the elevator has descended from floor 3 to floor 0, and lines 30-34 show that the client chooses the request to visit floor 1.

Thus we see that from digital twin to PLC to Modbus client the information and control flows appear to be working as designed.k

