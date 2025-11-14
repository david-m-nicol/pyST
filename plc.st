PROGRAM plc0
  VAR
    sys_state AT %IX0.0 : BOOL := TRUE;
    floor_req AT %IX0.1 : ARRAY[0..3] OF BOOL := [FALSE, FALSE, FALSE, FALSE];
    door_closed AT %IX0.5 : BOOL := TRUE;
    moving_up AT %IX0.6 : BOOL := FALSE;
    moving_down AT %IX0.7 : BOOL := FALSE;

    floor_level AT %IW0 : INT := 0;

    sys_on AT %QX0.0 : BOOL := TRUE; 
    open_cmd  AT %QX0.1 : BOOL := FALSE;
    close_cmd AT %QX0.2 : BOOL := FALSE;
    move_up_cmd AT %QX0.3 : BOOL   := FALSE;
    move_down_cmd AT %QX0.4 : BOOL := FALSE;
  
    logic_state AT %MW0 : INT := 0;
    target_flr_code AT %MW1 : INT := 0;
	obs_target_flr_code AT %MW2 : INT := 0;
    target_flr AT %MW3 : INT := 0;
    target_level AT %MW4 : INT := 0;
    current_flr AT %MW5 : INT := 0;
    count_down AT %MW6 : INT := 0;

    ms_per_cycle AT %MW7 : INT := 100;

    mb_import : IMPORT_FROM_MB;
    mb_export : EXPORT_TO_MB;
  END_VAR

  // is the system 'on'
  mb_import(TABLE="COIL", IDX=0, LEN=1, VALUE=>sys_on);

  // the target_flr_code is non-zero when the controller has selected 
  // a floor and written its identity (plus 1) into the target_flr_code variable
  // 
  mb_import(TABLE="HOLDING_REG", IDX=0, LEN=1, VALUE=>obs_target_flr_code);
 
  IF obs_target_flr_code <> target_flr_code THEN
       target_flr_code := obs_target_flr_code;
  END_IF;

  CASE logic_state OF
    0:  // wait for client to select target floor
        IF target_flr_code > 0 THEN
			// floor is chosen so we compute the target level,
            // apply power, and change the logic_state
			//
			target_flr := target_flr_code-1
			IF target_flr < current_flr THEN 
				target_level := 4*target_flr + 1;
				move_down_cmd := TRUE; 
				move_up_cmd := FALSE; 
			ELSE
				target_level := 4*target_flr -1;
				move_up_cmd := TRUE; 
				move_down_cmd := FALSE; 
			END_IF;
			target_flr_code := 0;
			logic_state := 1;
		END_IF;
             
    1:  // wait to see that one of the power commands is high
        IF move_up_cmd = TRUE and moving_up = TRUE THEN
            logic_state := 2;
        END_IF;

        IF move_down_cmd = TRUE and moving_down = TRUE THEN
            logic_state := 2;
        END_IF;

    2: // await the observed floor level to hit target level
        IF floor_level = target_level THEN
            move_up_cmd := FALSE;
            move_down_cmd := FALSE;
            
            logic_state := 3;
        END_IF;

    3: // await seeing that the power is not on
        IF moving_up = FALSE AND moving_down = FALSE THEN
            open_cmd := TRUE; 
            current_flr := TO_INT(floor_level/4)
            logic_state := 4; 
        END_IF;

    4: // await seeing that the door has opened
        IF NOT door_closed THEN 
            logic_state := 5;
            count_down := 10;
            open_cmd := FALSE;
            close_cmd := FALSE;
        END_IF;

    5: // decrement count down and see if zero
        count_down := count_down - 1;
        IF count_down = 0 THEN
            logic_state := 6;
            close_cmd := TRUE;
            open_cmd := FALSE;
        END_IF;
   
    6: // await evidence that the door has closed
        IF door_closed = TRUE THEN
            logic_state := 0;
            close_cmd := FALSE;
        END_IF; 
    END_CASE;

  // report whether on or off
  mb_export(TABLE="DATA", IDX=0, VALUE := sys_state);

  // report whether door is closed
  mb_export(TABLE="DATA", IDX=1, VALUE := door_closed);

  // report whether in motion
  mb_export(TABLE="DATA", IDX=2, VALUE := moving_up or moving_down);
  
  // if the elevator is not moving, the floor is where the elevator car rests
  mb_export(TABLE="INPUT_REG", IDX=0, VALUE := current_flr);

  // if the elevator is not moving, the count_down is the number of milliseconds until the door closes
  mb_export(TABLE="INPUT_REG", IDX=1, VALUE := count_down*ms_per_cycle);

  // export the table of floor requests
  mb_export(TABLE="INPUT_REG", IDX=2, VALUE := floor_req, START=0, LEN=4);

  // export the communicated target floor code so that client knows it has been received
  mb_export(TABLE="HOLDING_REG", IDX=0, VALUE := obs_target_flr_code); 

END_PROGRAM

