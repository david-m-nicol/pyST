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
    target_flr AT %MW1 : INT := 0;
    target_level AT %MW2 : INT := 0;
    selections AT %MW3 : INT := 0;
    current_flr AT %MW4 : INT := 0;
    count_down AT %MW5 : INT := 0;

    mb_import : IMPORT_FROM_MB;
    mb_export : EXPORT_TO_MB;
  END_VAR

  mb_import(TABLE="COIL", IDX=0, VALUE=>sys_on);
      
  CASE logic_state OF
    0:  // see if there any selections above present  
        target_flr := -1;

        // loop up
        IF current_flr < 3 THEN
            FOR IDX:=current_flr+1 TO 3 DO
                IF floor_req[IDX] = TRUE THEN
                    target_flr := IDX
                    EXIT;              
                END_IF;
            END_FOR;
        END_IF;

        // look down
        IF target_flr = -1 and current_flr > 0 THEN
            FOR IDX:=0 TO current_flr-1 DO
                IF floor_req[IDX] = TRUE THEN
                    target_flr := IDX
                END_IF;
            END_FOR;
        END_IF;

        // if target_flr is not -1 we select the target level
        // and apply power and change the logic_state
        IF target_flr <> -1 THEN
            IF target_flr < current_flr THEN 
                target_level := 4*target_flr + 1;
                move_down_cmd := TRUE; 
                move_up_cmd := FALSE; 
            ELSE
                target_level := 4*target_flr -1;
                move_up_cmd := TRUE; 
                move_down_cmd := FALSE; 
            END_IF;

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

  mb_export(TABLE="DATA", IDX=0, VALUE := sys_state);
  mb_export(TABLE="DATA", IDX=1, VALUE := moving_up or moving_down);
  mb_export(TABLE="INPUT_REG", IDX=0, VALUE := logic_state);
  mb_export(TABLE="INPUT_REG", IDX=1, VALUE := floor_level);
  mb_export(TABLE="INPUT_REG", IDX=2, VALUE := target_level);

END_PROGRAM

