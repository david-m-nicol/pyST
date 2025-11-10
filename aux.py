# file to be copied into the python representation of the ST file
# being analyzed by pyST.py
#
# IMPORT_FROM_MB represents a function block callable from the ST program
#
class IMPORT_FROM_MB():
    def __init__(self):
        self.VALUE = None

    # when the function block is executed the 'call' method is used
    def call(self, TABLE='COIL', IDX=4):

        # TABLE is a string included by the ST programmer that identifies the Modbus
        # data table to import the value from
        match TABLE:
            case 'COIL':
                input_blk = mbd.coilblock
            case 'DATA':
                input_blk = mbd.datablock
            case 'INPUT_REG':
                input_blk = mbd.inputRegblock
            case 'HOLDING_REG':
                input_blk = mbd.holdingRegblock
            case _:
                print(f"unrecognized Modbus table {TABLE}")
                return

        # the file mbd.py has the code and global data structures through which
        # we interact with Modbus
        OK, values = mbd.getTableValues(input_blk, IDX, 1)
        if OK:
            self.VALUE = values[0] 
        else:
            print(f"Error importing from Modbus table {TABLE}") 


# EXPORT_TO_MB pushes the offered value out to the Modbus data table that is named,
# at the location that is named
#
class EXPORT_TO_MB():
    def __init__(self):
        self.value = None

    def call(self, VALUE=None, TABLE='COIL', IDX=4):
        match TABLE:
            case 'COIL':
                input_blk = mbd.coilblock
            case 'DATA':
                input_blk = mbd.datablock
            case 'INPUT_REG':
                input_blk = mbd.inputRegblock
            case 'HOLDING_REG':
                input_blk = mbd.holdingRegblock
            case _:
                print(f"unrecognized Modbus table {TABLE}")
                return

        OK = mbd.setTableValues(input_blk, IDX, [VALUE])
        if not OK:
            print(f"problem exporting value {VALUE} to Modbus table {TABLE}")


# pyST.py creates a json string that is converted to a dictionary
# to carry information about all of the global variables.
# build_loc_map calls the responsible interface-memory map structure's 'add_var' to register
# that variable
def build_loc_map(var_dict_list):
    global IX_seq, IW_seq, QX_seq, QW_seq
    global MW_seq, MD_seq, ML_seq

    for var_dict in var_dict_list:
        name = var_dict['name']
        pos = var_dict['pos']
        py_type = var_dict['py_type']
        var_type = var_dict['var_type']
        mem_code = var_dict['mem_code']
        value = var_dict['value']

        mem_class = mem_code[:2]
        mem_adrs = mem_code[2:]

        mb_idx   = var_dict['mb_idx']
        cmd = f"{mem_class}_seq.add_var(var_dict['name'], var_type, py_type, mem_class, mem_adrs, pos, mb_idx, value)" 

        exec(cmd)

# A call to top_of_cycle_import is embedded in the top of every PLC cycle
# to get values from value tables in IX and IW and put into the variables 
def top_of_cycle_import():
    IX_seq.intrfc_to_vars()
    IW_seq.intrfc_to_vars()

# A call to bottom_of_cycle_import is embedded in the bottom of every PLC cycle
# to export variables mapped to QX_seq and QW_seq
def bottom_of_cycle_export():
    # move the updates made on variables to the hardware interface
    QX_seq.vars_to_intrfc()
    QW_seq.vars_to_intrfc()

# take a string and an identifier of its python type to return
# data object in that type, with the named value
def typed_value(value, py_type):
    match py_type:
        case 'bool': 
            return bool(value)
        case 'int': 
            return int(value)
        case 'float': 
            return float(value)
        case 'str': 
            return str(value)

# the var_seq class represents IX, QW, etc. It holds a lock to protect it from
# concurrent access, a descriptin of the memory type of data it represents,
# and a list of subseq instances each of which represents a contiguous sequence
# of values
class var_seq():
    def __init__(self, var_type):
        self.var_type = var_type
        self.subseqs = []
        self.thrd_lock = threading.Lock()

    # add_var takes a description of a variable and works in a representation for that
    # variable in one of its subseq structures (which it may need to create)
    # The attributes of the variable so integrated are
    #       - name .  Note that pyST.py will create a name like 'pressure[3]' if there is
    #                 an array declared by the ST program.   
    #       - var_type . This is the variable's declared type in ST
    #       - py_type  . This is the type used in python to represent the variable
    #       - mem_class .  Two letter code like 'IX', 'MD' etc that ST used to map the variable to the interface
    #       - mem_adrs  . A string like '3' or '2.1' that is derived from the ST mapping
    #       - pos      . An integer that declares the variable's relative position in the subseq representation of variables
    #       - mb_idx   . The index of the variable in the Modbus table that also holds it, if any
    #       - value    . A representation of the initial values assigned to the variable  
    def add_var(self, name, var_type, py_type, mem_class, mem_adrs, pos, mb_idx, value):
        self.thrd_lock.acquire() 

        # use pos to look for the insertion point in the list of subseqs
        for idx in range(0, len(self.subseqs)):
            # pos specifies where in seq the variable sits
            if pos < self.subseqs[idx].first:
                # first subseq that dominates the location.
                # tack it on to the previous subseq?
                if idx>0 and self.subseqs[idx-1].last == pos-1:
                    # pos fits at tail of previous subseq
                    self.subseqs[idx-1].append_var(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)

                    # see if now the subseqs are adjacent 
                    if self.subseqs[idx-1].last+1 == self.subseqs[idx].first:
                        # they are adjacent, so combine them
                        self.subseqs[idx-1].last = self.subseqs[idx].last
                        self.subseqs[idx-1].names.extend(self.subseqs[idx].names)

                        # either truncate self.subseqs[idx], or pull in the subseqs beyond it 
                        if idx < len(self.subseqs)-1:
                            # there are subseqs with index larger than idx
                            tail = copy.copy(self.subseqs[idx+1:])
                            self.subseqs[:idx].extend(tail)
                        else:
                            # nothing beyond idx
                            self.subseqs = self.subseqs[:idx]

                    # done with merging adjacent subseqs
                    self.thrd_lock.release() 
                    return True
            
                # did not attach to previous subseq, does it attach to the one at idx?
                elif pos+1 == self.subseqs[idx].first:
                    # yes it does, so call add_var to put it in
                    self.subseqs[idx] = self.subseqs[idx].prepend_var(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)
                    self.thrd_lock.release() 
                    return True
                else:
                    # variable at location idx appears before the one at location idx
                    # make a new subseq containing only this variable
                    new_subseq = var_subseq(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)

                    # remember the subseq that follows the new one
                    if idx > 0:
                        # a subsequence behind the inserted subseq
                        tail = copy.copy(self.subseqs[idx:])
                        self.subseqs = self.subseqs[:idx].append(new_subseq)
                        self.subseqs.extend(tail)
                    else:
                        # inserted subseq goes to the front
                        tail = copy.copy(self.subseqs)
                        self.subseqs = [new_subseq]
                        self.subseqs.extend(tail)

                    self.thrd_lock.release() 
                    return True

            # pos is larger than the first element of the subseq indexed at idx.
            # error if it falls within that subseq
            elif pos <= self.subseqs[idx].last:
                print(f"variable at location {pos} already defined")
                self.thrd_lock.release() 
                return False

        # ran through the entire list of subseqs without finding a preceding subseq. 
        # if there was a last subseq see if this joins it
        if len(self.subseqs) > 0:
            if self.subseqs[-1].last+1 == pos:
                self.subseqs[-1].append_var(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)
                self.thrd_lock.release() 
                return True

        # no, so add a new one at the end
        new_subseq = var_subseq(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)
        self.subseqs.append(new_subseq)
        self.thrd_lock.release() 
        return True 

    # transfer the values of all variables represented to to the subseq data structure that represents them
    def vars_to_intrfc(self):
        self.thrd_lock.acquire() 
        for subseq in self.subseqs:
            subseq.import_values()
        self.thrd_lock.release() 

    # transfer the values of interface values mapped to this instance to their variable representation in the program
    def intrfc_to_vars(self):       
        self.thrd_lock.acquire() 
        for subseq in self.subseqs:
            subseq.export_vars()
        self.thrd_lock.release() 

    # look for a subseq list containing memory values in the indicated range
    # return whether successful and the range, or not.  Called by the digital twin
    # to acquire values from the interface list
    def read_values(self, first, last):
        values = []
        success = False
        self.thrd_lock.acquire() 

        # examine each subseq
        for subseq in self.subseqs:
            # does it contain the range of interest?
            if subseq.first <= first and last <= subseq.last:
                # yes, so copy the values in the interface list into the values list
                first_idx = first-subseq.first
                values = copy.copy(subseq.values[first_idx:last-first+1])
                success = True

        self.thrd_lock.release()

        # return the found values
        return success, values

    # look for a list containing memory values in the indicated range
    # and write.  Used by the digital twin to export its state to the interface
    def write_values(self, first, last, values):
        success = False
        self.thrd_lock.acquire() 

        for subseq in self.subseqs:
            # does this subseq contain the range of interest?
            if subseq.first <= first and last <= subseq.last:
                # yes, so write the range's values into the subseq values list
                jdx = 0
                for pos in range(first, last+1):
                    # calculate the position in the values list
                    idx = pos-subseq.first
            
                    # copy in the value
                    subseq.values[idx] = values[jdx]
                    jdx += 1

                success = True

        self.thrd_lock.release()
        return success


# The var_desc class holds a description of a variable.  The var_subseq structure
# holds an ordered list of these
# 
class var_desc():
    def __init__(self, name, py_type, mem_class, mem_adrs, pos, mb_idx):
        self.name = name
        self.py_type = py_type
        self.mem_class = mem_class
        self.mem_adrs = mem_adrs
        self.pos      = pos
        self.mb_idx = mb_idx

# The var_subseq class represents a sequence of variables that are contiguous
# in their ST memory class data structure
class var_subseq():
    def __init__(self, name, py_type, mem_class, mem_adrs, pos, mb_idx, value):

        # a subseq can represent a sequence of variables, but since we are just creating
        # new subseq instance the first and last elements have the same position in the ST memory
        # structure
        self.first = pos
        self.last  = pos

        # same is true for the mapping of this variable to Modbus
        self.mb_first = mb_idx
        self.mb_last  = mb_idx

        # initialize the list of variable descriptors with a list of a single element
        self.var_desc = [var_desc(name, py_type, mem_class, mem_adrs, pos, mb_idx)]

        match py_type:
            case 'int':
                value = int(value)
            case 'float':
                value = float(value)
            case 'bool':
                if not isinstance(value,bool):
                    if isinstance(value, int):
                        value = True if value%2 else False
                    elif isinstance(value,str):
                        if value in ('True','TRUE','true'):
                            value = True
                        elif value in ('False', 'FALSE', 'false'):
                            value = False  
            case 'byte':
                value = int(value)
                va = bytes([value])
                value = va[0] 

        self.values   = [value]

    # given a subseq instance to be adjoined from the right, combine its description
    # into the self instance
    def merge_var(self, successor):

        # adjust the indices of the last element
        self.last = successor.last
        self.mb_last = successor.mb_last

        # extend the values list by those of the successor
        self.values.extend(successor.values)

        # extend the list of variable descriptors by those of the successor
        self.var_desc.extend(successor.var_desc)

    # given a subseq instance on the right to be adjoined to, create it and merge
    # the self instance into it
    def append_var(self, name, py_type, mem_class, mem_adrs, pos, mb_idx, value):
        new_subseq = var_subseq(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)
        self.merge_var(new_subseq)
    
    # given a subseq instance on the left to be adjoined to, create it and merge the
    # self instance into it   
    def prepend_var(self, name, py_type, mem_class, mem_adrs, pos, mb_idx, value):
        new_subseq = var_subseq(name, py_type, mem_class, mem_adrs, pos, mb_idx, value)
        new_subseq.merge_var(self)
        return new_subseq

    # copy all the values in the variables into the values list
    def import_values(self):
        for idx in range(0, len(self.var_desc)):
            vard = self.var_desc[idx] 
            name = vard.name
            py_type = vard.py_type
            match py_type:
                case 'bool':
                    value = bool(eval(name))
                case 'int':
                    value = int(eval(name))
                case 'float':
                    value = float(eval(name))
                case 'str':
                    value = str(eval(name))
            
            self.values[idx] = value

    # export the values into to the named variables
    def export_vars(self):
        for idx in range(0, len(self.var_desc)):
            vard = self.var_desc[idx]
            name = vard.name
            py_type = vard.py_type
            value = self.values[idx]

            # names with '[' are array references
            if name.find('[') > 0:
                leftb  = name.find('[')+1
                rightb = name.find(']')
                jdx = int(name[leftb:rightb].strip())
                name = name[:leftb-1]
                globals()[name][jdx] = typed_value(value, py_type)
            else:
                globals()[name] = typed_value(value, py_type)

# create the global instances of the ST memory structures
IX_seq = var_seq('IX')
IW_seq = var_seq('IW')
QX_seq = var_seq('QX')
QW_seq = var_seq('QW')
MW_seq = var_seq('MW')
MD_seq = var_seq('MD')
ML_seq = var_seq('ML')

