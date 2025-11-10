import argparse
import re
import pdb
import sys
import json
import math
import copy

from pathlib import Path

st_file = ''
python_file = ''
location_file = ''
intrfc_file = ''

global_lines = []
global_vars  = []
global_stmnt = ''

functions = """
def MAX(a,b):
    return max(a,b)

def MIN(a,b):
    return min(a,b) 

def ABS(x):
    return abs(x)

def SQRT(x):
    return math.sqrt(x)

def EXPT(x, exp):
    return math.pow(x,exp)

def LN(x):
    return math.log(x)

def LOG(x):
    return math.log(x,10)

def EXP(x):
    return math.exp(x)

def SIN(x):
    return math.sin(x)

def COS(x):
    return math.cos(x)

def TAN(x):
    return math.tan(x)

def ASIN(x):
    return math.asin(x)
 
def ACOS(x):
    return math.acos(x)
 
def ATAN(x):
    return math.atan(x)

def LIMIT(mn, x, mx):
    if x < mn:
        return mn
    if mx < x:
        return mx
    return x

def TRUNC(x):
    return int(x)

def MOD(n,m):
    return n%m

def BOOL_TO_INT(b):
    return int(b)

def INT_TO_DINT(x):
    return x

def REAL_TO_INT(x):
    return int(x)

def TO_SINT(x):
    return int(x)

def TO_INT(x):
    return int(x)

def TO_DINT(x):
    return int(x)

def TO_LINT(x):
    return int(x)

def TO_REAL(x):
    return float(x)

def TO_STRING(x):
    return f"{x}"

def TO_WSTRING(x):
    return f"{x}"

def LEFT(s,L):
    return s[:L]

def RIGHT(s,L):
    n = len(s)
    return s[n-L:]

def MID(s, n, k):
    return s[k:k+n]

def LEN(s):
    return len(s)

def CONCAT(s1,s2):
    return s1+s2

def SEL(b, in0, in1):
    if b:
        return in1
    return in0

def MUX(*args):
    k = args[0]
    return args[k-1]

def MOVE(x):
    return x
"""

class var_seq():
    def __init__(self, var_type):
        self.var_type = var_type
        self.subseq = []
        
    def add_var(self, name, var_type, py_type, mem_code, value, var_array=False, array_len=0):
        # no memory class position if the length of the mem_code is just 2 for the memory class
        if len(mem_code) == 2:
            # add this to the end of the last existing subseq, if any
            if len(self.subseq) > 0: 
                self.add_var(name, var_type, py_type, mem_code, self.subseq[-1].last+1, value, \
                    var_array=var_array, array_len=array_len)
            else: 
                # nothing already in the sequence, so this goes first
                new_subseq = var_subseq(name, var_type, py_type, mem_code, 0, value, \
                    var_array=var_array, array_len=array_len)

            return True
   
        else:
            # memory address is specified
            pos = mem_code[2:] 
            pieces = pos.split('.')
            if len(pieces) == 1:
                pos = int(pos)
            else:  
                word = int(pieces[0])
                bit  = int(pieces[1]) 
                pos = 8*word+bit

        # if the memory address is specified the user has to get it right, no error checking here
        for idx in range(0, len(self.subseq)):
            # find where to insert it
            if pos+array_len < self.subseq[idx].first: 
                # first subseq that dominates the location.
                # tack it on to the previous subseq?
                if idx>0 and self.subseq[idx-1].last == pos-1+array_len:
                    # loc fits at tail of previous subseq
                    self.subseq[idx-1].append_var(name, var_type, py_type, mem_code, pos, value, \
                        var_array=var_array, array_len=array_len)

                    # see if now the subseqs are adjacent 
                    if self.subseq[idx-1].last+1 == self.subseq[idx].first:
                        # they are adjacent, so combine them
                        self.subseq[idx-1].merge_var(self.subseq[idx])

                        # either truncate self.subseq[idx], or pull in the subseqs beyond it 
                        if idx < len(self.subseq)-1:
                            # there are subseqs with index larger than idx
                            tail = copy.copy(self.subseq[idx+1:])
                            self.subseq[:idx].extend(tail)
                        else:
                            # nothing beyond idx
                            self.subseq = self.subseq[:idx]

                    # done with merging adjacent subseqs
                    return True
            
                # did not attach to previous subseq, does it attach to the one at idx?
                elif pos+array_len+1 == self.subseq[idx].first:
                    # yes it does, so call add_var to put it in
                    self.subseq[idx] = self.subseq[idx].prepend_var(name, var_type, py_type, mem_code, pos, value,\
                        var_array=var_array, array_len=array_len)

                    return True
                else:
                    # variable at location idx appears before the one at location idx
                    # make a new subseq containing only this variable
                    new_subseq = var_subseq(name, var_type, py_type, mem_code, pos, value, \
                        var_array=var_array, array_len=array_len)

                    # remember the subseq that follows the new one
                    if idx > 0:
                        # a subsequence behind the inserted subseq
                        tail = copy.copy(self.subseq[idx:])
                        self.subseq = self.subseq[:idx].append(new_subseq)
                        self.subseq.extend(tail)
                    else:
                        # inserted subseq goes to the front
                        tail = copy.copy(self.subseq)
                        self.subseq = [new_subseq]
                        self.subseq.extend(tail)

                    return True

            # loc is larger than the first element of the subseq indexed at idx.
            # error if it falls within that subseq
            elif pos+array_len <= self.subseq[idx].last:
                print(f"variable of type {self.var_type} at location {pos} already defined")
                return False

        # ran through the entire list of subseqs without finding a preceding subseq. 
        # if there was a last subseq see if this joins it
        if len(self.subseq) > 0:
            if self.subseq[-1].last+1 == pos:
                self.subseq[-1].append_var(name, var_type, py_type, mem_code, pos, value, \
                    var_array=var_array, array_len=array_len)
                return True

        # no, so add a new one at the end
        new_subseq = var_subseq(name, var_type, py_type, mem_code, pos, value, \
            var_array=var_array, array_len=array_len)
        self.subseq.append(new_subseq)
        return True 

    def import_values(self):
        for subseq in self.subseq:
            subseq.import_values()

    def export_vars(self):       
        for subseq in self.subseq:
            subseq.export_vars()


class var_desc():
    def __init__(self, name, var_type, py_type, mem_code):
        self.name = name
        self.var_type = var_type
        self.py_type  = py_type
        self.mem_code = mem_code

class var_subseq():
    def __init__(self, name, var_type, py_type, mem_code, pos, value, var_array=False, array_len=0):
        self.first = pos
        if array_len > 0:
            self.last  = pos+array_len-1
        else:
            self.last = pos

        array_len = array_len 

        self.mb_first = None
        self.mb_last  = None
    
        if not var_array:
            vard = var_desc(name, var_type, py_type, mem_code)
            self.vards    = [vard]
            self.values   = [value]
        else:
            self.vards = []
            self.values = []
            for idx in range(0, array_len):
                if mem_code is not None and mem_code != '':
                    this_mem_code = mem_code_adv(mem_code,idx)
                else:
                    this_mem_code = None

                vard = var_desc(f"{name}[{idx}]", var_type, py_type, this_mem_code)
                self.vards.append(vard)
                if len(value) > 0:
                    self.values.append(value[idx])

        if self.last-self.first+1 != len(self.values):
            print('oops')
            x = 4

    def merge_var(self, successor):
        if self.last-self.first+1 != len(self.values):
            print('oops')
            x = 5

        self.last = successor.last
        self.mb_last = successor.mb_last
        self.values.extend(successor.values)
        self.vards.extend(successor.vards)

        if self.last-self.first+1 != len(self.values):
            print('oops')
            x = 6


    def append_var(self, name, var_type, py_type, mem_code, pos, value, var_array=False, array_len=0):
        new_subseq = var_subseq(name, var_type, py_type, mem_code, pos, value, var_array=var_array, array_len=array_len)
        self.merge_var(new_subseq)
    
    def prepend_var(self, name, var_type, py_type, mem_code, pos, value, var_array=False, array_len=0):
        new_subseq = var_subseq(name, var_type, py_type, mem_code, pos, value, var_array=var_array, array_len=array_len)
        new_subseq.merge_var(self)
        return new_subseq

    # copy the values in the variables into the values list
    def import_values(self):
        self.values = []
        for name in self.names:
            value = eval(name)
            self.values.append(value)

    # export the values into to the named variables
    def export_vars(self):
        for idx in range(0, len(self.names)):
            name = self.names[idx]
            globals()[name] = self.values[idx]


def check_values(vlist):
    for idx in range(0, len(vlist)):
        v= vlist[idx]
        if isinstance(v,str):
            return
        if isinstance(v,int):
            return
        if isinstance(v,float):
            return
        
        pdb.set_trace()
        x=3
  
 

IX_seq = var_seq('IX')
IW_seq = var_seq('IW')
QX_seq = var_seq('QX')
QW_seq = var_seq('QW')
MW_seq = var_seq('MW')
MD_seq = var_seq('MD')
ML_seq = var_seq('ML')


var_types = ('BOOL', \
    'SINT', 'INT', 'DINT', 'LINT', \
    'USINT', 'UINT', 'UDINT', 'ULINT', \
    'BYTE', 'WORD', 'DWORD', 'LWORD', \
    'REAL', 'LREAL', \
    'STRING', 'WSTRING', \
    'TIME', 'TOD', 'DATE', 'DTL')

python_type = {
    'BOOL':'bool', 
    'SINT':'int', 
    'INT':'int',
    'DINT':'int',
    'LINT':'int',
    'USINT':'int',
    'UINT': 'int',
    'UDINT': 'int',
    'ULINT': 'int',
    'BYTE': 'byte',
    'WORD':'int',
    'DWORD':'int',
    'LWORD':'int',
    'REAL':'int',
    'LREAL':'int',
    'STRING':'int',
    'WSTRING':'str', 
    'TIME':'str',
    'TOD':'str',
    'DATE':'str',
    'DTL':'str'}


type_to_size = {'SINT':'MW', 'INT':'MW', 'DINT':'MD', 'LINT':'ML',\
    'USINT':'MW', 'UINT':'MW', 'UDINT': 'MD', 'ULINT':'ML', \
    'BYTE':'MW', 'WORD':'MW', 'DWORD':'MD', 'LWORD': 'ML',
    'REAL': 'MD', 'LREAL':'ML',
    'STRING':'MW', 'WSTRING':'MW'}


fb_types = ('TON', 'TOF', 'TP', 'CTU', 'CTD', 'PULSE_GEN', \
    'CTUD', 'RS', 'SR', 'F_TRIG', 'R_TRIG', 'IMPORT_FROM_MB', 'EXPORT_TO_MB')


class Variable:
    def __init__(self, name, var_type, mem_code, value, var_array=False, array_len=0): 

        self.name = name.upper()

        self.var_type = var_type.upper()
        self.var_type = self.var_type.replace(';','')
        self.var_array   = var_array
        self.array_len   = array_len

        if self.var_type in python_type:
            py_type = python_type[self.var_type]
        else:
            py_type = 'class'

        if value is not None:
            value = value.replace(';','')

        if var_type in var_types: 
            if var_array and value is not None and len(value) > 0:
                var_value = value.replace(';','')
                var_value = value.replace('[','')
                var_value = var_value.replace(']','')

                values = var_value.split(',')
                value_list = []
                for idx in range(0, array_len):
                    match py_type:
                        case 'bool':
                            value_list.append(bool(values[idx]))
                        case 'int' | 'byte':
                            value_list.append(int(values[idx]))
                        case 'float':
                            value_list.append(float(values[idx]))
                        case 'str':
                            value_list.append(str(values[idx]))

                if py_type == 'byte':
                    self.value = bytes(value_list)
                else:
                    self.value = value_list 

            elif value is not None:
                match py_type:
                    case 'int':
                        self.value = int(value)
                    case 'float':
                        self.value = float(value)
                    case 'str':
                        self.value = value
                    case 'bool':
                        if value in ('TRUE','True','true'):
                            self.value = 'True' 
                        elif value in ('FALSE', 'False', 'false'):
                            self.value = 'False'
                        else:
                            pdb.set_trace()
                            x= -1
                    case 'byte':
                        values = bytes([value])
                        self.value = values[0]
            else:
                self.value = None
        elif var_type in fb_types:
            self.value = value
        else:
            self.value = None

        # put this variable in the right mapping class
        if not mem_code is None:
            mem_code = mem_code.replace('%','')
            mem_class = mem_code[:2]
        else:
            if self.var_type in type_to_size: 
                mem_class = type_to_size[self.var_type]
                mem_code  = mem_class
            else:
                return

        match mem_class:
            case 'QX':
                QX_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case 'IX':
                IX_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len )
            case 'IW':
                IW_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case 'QW':
                QW_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case 'MW':
                MW_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case 'MD':
                MD_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case 'ML':
                ML_seq.add_var(name, var_type, py_type, mem_code, self.value, var_array=var_array, array_len=array_len)
            case _:
                print(f"unrecognized PLC address {adrs}")
                return  

global_stmnt = ''

def clean_value(value):

    if isinstance(value,bool):
        return 'True' if value else 'False'

    if not isinstance(value, str):
        return value

    if value.lower() == 'false':
        return 'False'
    if value.lower() == 'true':
        return 'True'
    return value

class ConvertorApp:
    def __init__(self, st_file):
        self.st_file = st_file

    def convert(self):
        with open(self.st_file,'r') as rf:
            st_code = rf.read()

        converted_code = self.convert_st_to_python(st_code)
        #converted_code = self.clean_up_python_code(converted_code)
        return converted_code

    def convert_st_to_python(self, st_code):
        global global_stmnt, global_vars

        variables = {}

        # get rid of configuration block if present
        config_pattern = r"CONFIGURATION(.*?)END_CONFIGURATION"
        config_match = re.search(config_pattern, st_code, re.DOTALL)
        if config_match:
            st_code = re.sub(config_pattern, '', st_code, flags=re.DOTALL)

        # scrap off PROGRAM and END_PROGRAM
        st_code = st_code.replace('END_PROGRAM','')

        first = st_code.find('PROGRAM')
        last  = st_code[first:].find('\n')
        if first>0:
            front = st_code[:first-1]
        else:
            front = ''
        back  = st_code[last+1:]
        st_code = front+back

        # replace line by line comment
        lines = st_code.split('\n')
        trans = []
        for line in lines: 
            if line.find('(*') > -1:
                first = line.find('(*')
                last  = line.find('*)')
                line = line[:first]+'//'+line[first+2:last] 
            trans.append(line)

        st_code = '\n'.join(trans)
 
        var_blk_desc = (\
            ('all', r"VAR\s+(.*?)END_VAR"),\
            ('input', r"VAR_INPUT (.*?)END_VAR"), \
            ('output', r"VAR_OUTPUT (.*?)END_VAR"), \
            ('in_out', r"VAR_IN_OUT (.*?)END_VAR"), \
            ('global', r"VAR_GLOBAL (.*?)END_VAR"), \
            ('external', r"VAR_EXTERNAL (.*?)END_VAR"), \
            ('temp', r"VAR_TEMP (.*?)END_VAR"))

        ret_code = ""
        python_code = ""
    
        for var_class, var_declaration_pattern in var_blk_desc:

            # for each variable block type find all instances
            var_blks = re.finditer(var_declaration_pattern, st_code, re.IGNORECASE | re.DOTALL)
            holding = []
            for var_blk in var_blks:
                holding.append(var_blk)     
        
            var_blks = reversed(holding)
            for var_declaration in var_blks:    
                (start, end) = var_declaration.span()
                remainder = st_code[end+1:]

                var_blk = var_declaration.group(1)

                #trans_lines = ['!@!START_BLK']
                var_lines = var_blk.split('\n')
                for line in var_lines:
                    if len(line)>0:
                        line = line.strip()
                        if line.startswith('//'):
                            global_lines.append(line.replace(';',''))
                            continue

                        # look for an ARRAY declaration
                        if line.find('ARRAY[') == -1:
                            # look for initial assignments 
                            split_line = line.split(":=", maxsplit=1)
                            if len(split_line) > 1:

                                # var_value is the initialization value
                                var_first, var_value = split_line
                                var_value = var_value.strip()
                                if var_value.find('//') > -1:
                                    var_value = var_value[:var_value.find('//')]
                               
                                var_value = clean_value(var_value) 

                                var_name, var_type = var_first.split(":", maxsplit=1)

                                var_type = var_type.replace(';','')
                                var_type = var_type.strip()
                                if var_type.find('//') > -1:
                                    var_type = var_type[:var_type.find('//')]
                                var_type = var_type.strip()

                                var_name = var_name.strip()

                                mem_code = None
                                if var_name.find(' AT %') > -1:
                                    idx      = var_name.find(' %') 
                                    mem_code = var_name[idx+2:].strip() 
                                    var_name = var_name[:var_name.find(' AT %')].strip()
                                 
                                vname_list = var_name.split(',')
                                
                                for vname in vname_list:   
                                    # variables indexed by name gives the variable type, which might be a function block
                                    variables[vname] = Variable(vname, var_type, mem_code, \
                                        var_value, var_array=False, array_len=0)

                                var_name = var_name.replace(',','=')

                                new_line = f"{var_name} = {var_value}"
                                global_vars.append(var_name)

                                if line.find('//') > -1:
                                    new_line = new_line + line[line.find('//'):]

                                global_lines.append(new_line.replace(';',''))

                            else:
                                var_value = None
                                var_declaration = split_line[0]

                                if var_declaration.find(':') > -1:
                                    var_name, var_type = var_declaration.split(":", maxsplit=1)

                                    var_type = var_type.replace(';','')
                                    if var_type.find('//') > -1:
                                        var_type = var_type[:var_type.find('//')]
                                    var_type = var_type.strip()

                                    var_name = var_name.strip()
                                    mem_code = None
                                    if var_name.find(' AT %') > -1:
                                        idx = var_name.find(' %') 
                                        mem_code = var_name[idx+3:].strip() 

                                    var_value = clean_value(var_value)
     
                                    if var_type not in var_types and var_type not in fb_types:
                                        print(f"Variable {var_name} with unrecognized type {var_type}")
                                        var_value = None

                                    value = None
                                    if var_type in fb_types:
                                        var_value = f"{var_type}()"

                                    variables[var_name] = Variable(var_name, var_type, mem_code, \
                                        var_value, var_array=False, array_len=0)

                                    var_name = var_name.replace(',','=')
                                    global_vars.append(var_name)
                                    new_line = f"{var_name} = {var_value}"
                                    global_lines.append(new_line)

                        elif line.find('ARRAY[') > -1:
                            # look for initial assignments 
                            split_line = line.split(":=", maxsplit=1)
                            if len(split_line) > 1:

                                # var_value is the initialization value
                                var_first, var_value = split_line
                                var_value = var_value.strip()
                                if var_value.find('//') > -1:
                                    var_value = var_value[:var_value.find('//')]
                                var_value = var_value.replace(';','') 
                                var_name, var_array = var_first.split(":", maxsplit=1)
                                leftb  = var_array.find('[')
                                rightb = var_array.find(']') 
                                idx_rng = var_array[leftb+1:rightb]
                                lefti, righti = idx_rng.split('..')
                                left_idx  = int(lefti)
                                right_idx = int(righti)

                                if left_idx != 0:
                                    print(f"arrays start at index 0: {line.strip()}")
                                    exit(1)

                                type_idx  = var_array.find(' OF ')
                                var_type  = var_array[type_idx+4:].strip()
                                var_type = var_type.replace(';','')

                                var_type = var_type.strip()
                                var_name = var_name.strip()

                                mem_code = None
                                if var_name.find(' AT %') > -1:
                                    idx      = var_name.find(' %') 
                                    mem_code = var_name[idx+2:].strip() 
                                    var_name = var_name[:var_name.find(' AT %')].strip()
                                 
                                vname_list = var_name.split(',')
                                
                                for vname in vname_list:   
                                    # variables indexed by name gives the variable type, which might be a function block
                                    variables[vname] = Variable(vname, var_type, mem_code, \
                                        var_value, var_array=True, array_len=right_idx+1)

                                var_name = var_name.replace(',','=')

                                new_line = f"{var_name} = {var_value}"
                                global_vars.append(var_name)

                                if line.find('//') > -1:
                                    new_line = new_line + line[line.find('//'):]

                                global_lines.append(new_line.replace(';',''))

                            else:
                                var_value = None
                                var_declaration = split_line[0]

                                if var_declaration.find(':') > -1:
                                    var_name, var_array = var_first.split(":", maxsplit=1)
                                    leftb  = var_array.find('[')
                                    rightb = var_array.find(']') 
                                    idx_rng = var_array[leftb+1:rightb]
                                    lefti, righti = idx_rng.split('..')
                                    left_idx  = int(lefti)
                                    right_idx = int(righti)

                                    if left_idx != 0:
                                        print(f"arrays start at index 0: {line.strip()}")
                                        exit(1)

                                    type_idx  = var_array.find(' OF ')
                                    var_type  = var_array[type_idx+4:].strip()
                                    var_type = var_type.replace(';','')

                                    var_type = var_type.strip()

                                    var_name = var_name.strip()

                                    mem_code = None
     
                                    if var_type not in var_types:
                                        print(f"Variable {var_name} with unrecognized type {var_type}")
                                        var_value = None

                                    variables[var_name] = Variable(var_name, var_type, \
                                        mem_code, None, var_array=True, array_len=right_idx+1) 

                                    var_name = var_name.replace(',','=')
                                    global_vars.append(var_name)
                                    new_line = f"{var_name} = []"
                                    global_lines.append(new_line)
                        else:
                            new_line = split_line[0]
                            global_lines.append(new_line.replace(';',''))

                #trans_lines.append('!@!END_BLK\n')
                #trans_blk = '\n'.join(trans_lines)+'\n!@!START_BLK\n!@!START_MAIN\n!@!START_BLK\n'
                trans_blk = '\n'+'\n!@!START_BLK\n!@!START_MAIN\n!@!START_BLK\n'

                st_code = st_code[:start]+trans_blk+st_code[end+1:]

        end_var = st_code.find('!@!START_BLK\n!@!START_MAIN')
        var_blks = st_code[:end_var]+'!@!START_BLK\n!@!START_MAIN\n'

        global_decl = []
        for idx in range(0, len(global_vars), 5):
            stmnt = 'global '
            stmnt += ','.join(global_vars[idx:min(idx+5,len(global_vars))])
            global_decl.append(stmnt)

        global_stmnt = '\n'.join(global_decl)

        main_prg = remainder

        # convert the rest of it
        main_prg = self.convert_segment(variables, main_prg)
        main_prg = var_blks+main_prg
 
        return main_prg

    def convert_segment(self, var_dict, code):
        # find outside construct, if any
        first_if = code.find('IF')
        first_case = code.find('CASE')

        first_for = code.find('FOR')
        first_while = code.find('WHILE')
        first_repeat = code.find('REPEAT')

        code_type = None
        first_idx = -1

        if first_if > -1:
            code_type = 'IF'
            first_idx = first_if

        if first_case > -1 and (code_type is None or first_case < first_idx):
            code_type = 'CASE'
            first_idx = first_case

        if first_for > -1 and (code_type is None or first_for < first_idx):
            code_type = 'FOR'
            first_idx = first_for

        if first_while > -1 and (code_type is None or first_while < first_idx):
            code_type = 'WHILE'
            first_idx = first_while

        if first_repeat > -1 and (code_type is None or first_repeat < first_idx):
            code_type = 'REPEAT'
            first_idx = first_repeat

        # convert the lines prior to the first control structure
        if code_type is not None:
            trans_code = self.convert_statements(var_dict, code[:first_idx])
        else:
            # convert the whole thing
            trans_code = self.convert_statements(var_dict, code)
            return trans_code
    
        match code_type:
            # the first control structure is an IF
            case 'IF':
                outside_if     = first_idx
                outside_then   = code.find(' THEN')

                # find all END_IFs between outside_if and the end of the code
                endifs = find_instances('END_IF;', code, outside_if+1)

                outside_endif = None
                # find first one for which the number of intervening IF/END_IF's are equal
                for endif_instance in endifs: 
                    ifs    = find_instances('IF ', code, outside_if+1, endif_instance)
                    inner_endifs = find_instances('END_IF;', code, outside_if+1, endif_instance)

                    if len(ifs) == len(inner_endifs):
                        outside_endif = endif_instance
                        break

                if outside_endif is None:
                    print("ouch 1")
                    pdb.set_trace()
                    print("ouch 1")

                if_cond        = get_condition(code[outside_if+2:outside_then])
                trans_code     += 'if '+if_cond+' :\n!@!START_BLK'
            
                # see if there is an ELSE between outside_then and outside_endif
                outside_else = None
                #first_else = code[outside_then+4:outside_endif].find('ELSE')
                first_else = code.find('ELSE', outside_then+4, outside_endif)

                if first_else > -1:
                    # count the 'IF ' and 'END_IF;' between what follows THEN
                    # and the outside_if
                    ifs = find_instances('IF ', code, outside_then+4, outside_endif)
                    endifs = find_instances('END_IF;', code, outside_then+4, outside_endif)

                    # the ifs and endifs are non-zero and match we want to transform the body
                    if len(ifs) > 0 and len(ifs) == len(endifs):
                        trans_code += self.convert_segment(var_dict, code[outside_then+4:outside_endif])+'\n!@!END_BLK\n'
                    else:
                        # nothing in between so transfrom from after THEN to ELSE
                        # convert the segment between outside_then+4 and outside_else
                        trans_code += self.convert_segment(var_dict, code[outside_then+4:first_else])+'\n!@!END_BLK\n'
                        trans_code += 'else:\n!@!START_BLK'

                        # convert the segment between outside_else+4 and outside_endif
                        trans_code += self.convert_segment(var_dict, code[first_else+4:outside_endif])+'\n!@!END_BLK\n'

                else:
                    # no elses
                    trans_code += self.convert_segment(var_dict, code[outside_then+4:outside_endif])+'\n!@!END_BLK\n'
    
                # convert the rest of the code
                trans_code += self.convert_segment(var_dict, code[outside_endif+6:])
                return trans_code

            case 'CASE':
                outside_case   = first_idx
                case_end       = code.rfind('END_CASE;')

                of_key         = code.find(' OF')
                case_check     = code[first_idx+4:of_key]
                trans_match    = case_check.strip()

                case_block     = code[of_key+2:case_end]

                trans_code     += f"match {case_check}:\n!@!START_BLK\n"

                # strip the lines of the case_block of any comments
                case_block = strip_comments(case_block)

                # find the case markers
                cmp = r"[a-zA-Z0-9_]+:[^=]"
                cases = re.finditer(cmp, case_block, re.IGNORECASE | re.DOTALL)
                   
                markers = [] 
                for choice in cases:
                    (bm, end) = choice.span()
                    for idx in range(bm+1,end):
                        if case_block[idx] == ':':
                            markers.append((bm,idx)) 

                # create the case descriptions
                case_rep = [] 
                for idx in range (0, len(markers)):
                    (start_cond, end_cond) = markers[idx]
                    cond = case_block[start_cond:end_cond]
 
                    if idx < len(markers)-1:
                        block = case_block[end_cond+1:markers[idx+1][0]]
                    else:
                        block = case_block[end_cond+1:]

                    block += '!@!END_BLK\n'
                    case_rep.append((cond, block)) 

                for (cond, block) in case_rep: 
                    trans_code += f"case {cond}:\n!@!START_BLK"
                    trans_code += self.convert_segment(var_dict, block)

                trans_code = trans_code+'\n!@!END_BLK\n'+self.convert_segment(var_dict, code[case_end+8:])
                return trans_code

            case 'FOR':
                #for_loop_pattern = r"FOR\s+(.*?)\s*:=\s*(.*?)\s+TO\s+(.*?)\s+DO\s+(.*?)\s+END_FOR"
                for_loop_pattern = r"FOR\s+(.*?)\s*:=\s*(.*?)\s+TO\s+(.*?)\s+DO"
                for_loop = re.search(for_loop_pattern, code)
                loop_var = for_loop.group(1)
                loop_lower = for_loop.group(2)
                loop_upper = for_loop.group(3)
                loop_inc = None 
                
                # if loop_upper has BY in it we need to peel off the
                # limit and and put in the increment
                by_idx = loop_upper.find(' BY')
                if by_idx > -1:
                    limit = loop_upper[:by_idx].strip()
                    loop_inc = loop_upper[by_idx+3:].strip()
                    neg_inc = loop_inc.find('-') > -1
                    loop_inc = loop_inc.replace('-','') 
                    loop_upper = limit
 
                outside_for = code.find('FOR ') 
                outside_do  = code.find(' DO', outside_for+4)
                
                # find all the END_FOR;  from outside_for to the end of the code 
                endfors = find_instances('END_FOR;', code, outside_for+4)

                # find the first where the number of FOR and END_FOR between it and the 
                # outside FOR balance each other
                 
                outside_endfor = None
                # find first one for which the number of intervening FOR/END_FORs are equal
                for endfor_instance in endfors: 
                    fors    = find_instances('FOR ',     code, outside_for+4, endfor_instance)
                    endfors = find_instances('END_FOR;', code, outside_for+4, endfor_instance)
                    if len(fors) == len(endfors):
                        outside_endfor = endfor_instance
                        break

                # the body of the for loop is between outside_do + 3 and outside_endfor
                for_body = code[outside_do+3:outside_endfor]
           
                if loop_inc is None:
                    trans_code += f"for {loop_var} in range({loop_lower}, ({loop_upper})+1):\n!@!START_BLK"
                else:
                    trans_code += f"for {loop_var} in reversed(range({loop_upper}, ({loop_lower})+1,{loop_inc})):\n!@!START_BLK"

                trans_code += self.convert_segment(var_dict, for_body)+'\n!@!END_BLK\n' 
                trans_code += self.convert_segment(var_dict, code[outside_endfor+7:])
                return trans_code

            case 'WHILE':
                while_loop_pattern = r"WHILE\s+(.*?)\s+DO"
                while_loop = re.search(while_loop_pattern, code)
                loop_var = while_loop.group(1)

                outside_while = code.find('WHILE ') 
                outside_do    = code.find(' DO',outside_while+6)
                 
                # find all the END_WHILE;  from outside_do to the end of the code 
                endwhiles = find_instances('END_WHILE;', code, outside_while+6)

                # find the first where the number of WHILE and END_WHILE between it and the 
                # outside WHILE balance each other
                 
                outside_endwhile = None
                # find first one while which the number of intervening FOR/END_FORs are equal
                for endwhile_instance in endwhiles: 
                    whiles    = find_instances('WHILE ', code, outside_while+6, endwhile_instance)
                    endwhiles = find_instances('END_WHILE ', code, outside_while+6, endwhile_instance)

                    if len(whiles) == len(endwhiles):
                        outside_endwhile = endwhile_instance
                        break

                # the body of the while loop is between outside_do + 3 and outside_endwhile
                while_body = code[outside_do+3:outside_endwhile]

                trans_code += f"while {loop_var}:\n!@!START_BLK"
                trans_code += self.convert_segment(var_dict, while_body)+'\n!@!END_BLK\n' 
                trans_code += self.convert_segment(var_dict, code[outside_endwhile+9:])
                return trans_code

            case 'REPEAT':
                repeat_loop_pattern = r"REPEAT\s+(.*?)UNTIL\s+"
                outside_repeat = code.find("REPEAT")

                # find all the UNTILs;  from outside_repeat to the end of the code 
                untils = find_instances('UNTIL', code, outside_repeat+6)

                # find the first where the number of REPEAT and END_REPEAT between it and the 
                # outside REPEAT balance each other
                 
                outside_until = None
                # find first repeat which the number of intervening REPEAT/END_REPEAT are equal
                for until_instance in untils: 
                    repeats    = find_instances('REPEAT ', code, outside_repeat+6, until_instance)
                    endrepeats = find_instances('END_REPEAT;', code, outside_repeat+6, until_instance)

                    if len(repeats) == len(endrepeats):
                        outside_until = until_instance
                        break

                # the body of the repeat loop is between outside_repeat + 6 and outside_until
                outside_endrepeat = code.find('END_REPEAT;',outside_until+5)
                condition = code[outside_until+5:outside_endrepeat].strip()

                repeat_body = code[outside_repeat+6:outside_until]

                trans_code += f"while True:\n!@!START_BLK\n"
                trans_code += self.convert_segment(var_dict, repeat_body)+'\n' 
                trans_code += f"if {condition}:\n!@!START_BLK\nbreak\n!@!END_BLK\n!@!END_BLK"
                trans_code += self.convert_segment(var_dict, code[outside_endrepeat+11:])
                return trans_code

    
    def convert_statements(self, var_dict, code):
        lines = code.split('\n')

        rtn = []
 
        statements = code.split(';')
        for statement in statements:
            # if an assignment, change the assignment operator
            if statement.find(':=') > -1:
                statement = statement.replace(':=', '=')
                statement = statement.replace('<>', '!=')

            # if a call to a function block, alter
            words = statement.split()

            # look for instances where a FB variable looks like it is being called
            for word in words: 
                for var_name, var_inst in var_dict.items():
                    tst_var_name = var_name+'('
                    #if word.find(tst_var_name) > -1 and var_inst.vclass is not None:
                    if word.find(tst_var_name) > -1: 
                        statement = statement.replace(var_name, var_name+'.call')
                        break 

            rtn.append(statement)
        
            
        return ' '.join(rtn)

    def convert_fb(self, var_dict, st_code):
        lines = st_code.split('\n')
        rtn = []
        for line in lines:
            trimmed = line
            if line.find('//') > -1:
                trimmed = line[: line.find('//')]

            words = trimmed.split()
            # look for instances where a FB variable looks like it is being called
            for word in words: 
                for var_name, var_inst in var_dict.items():
                    tst_var_name = var_name+'('
                    if word.find(tst_var_name) > -1:
                        line = line.replace(var_name, var_name+'.call')
                        break 

            rtn.append(line)
            
        return '\n'.join(rtn)     

    def clean_up_python_code(self, python_code):

        # Replace ST keywords with Python keywords...
        python_code = re.sub(r"\bRETURN\b", "return", python_code, flags=re.IGNORECASE)
        python_code = re.sub(r"\bEXIT\b", "break", python_code, flags=re.IGNORECASE)
        python_code = re.sub(r"\bfalse\b", "False", python_code, flags=re.IGNORECASE)
        python_code = re.sub(r"\btrue\b", "True", python_code, flags=re.IGNORECASE)
        python_code = re.sub(r"\b AND \b", " and ", python_code)
        python_code = re.sub(r"\b OR \b", " or ", python_code)
        python_code = re.sub(r"\b NOT \b", " not ", python_code)

        python_code = python_code.replace(":=", "=")
        python_code = python_code.replace("<>", "!=")
        python_code = python_code.replace(";", "")
        python_code = python_code.replace("?", ":")
        python_code = python_code.strip()

        # Add newline at the end if not present
        if not python_code.endswith("\n"):
            python_code += "\n"

        # convert in-line comments
        python_code = python_code.replace('//','#')

        org_lines = python_code.split('\n')
        rtn = []
        empty_cnt = 0
        for line in org_lines:
            stripped = re.sub(r'\s+', '', line)
            if len(stripped) > 0:
                rtn.append(line)
                continue
            if empty_cnt < 2:
                rtn.append('')
            empty_cnt += 1

        return '\n'.join(rtn)

def fb_calls(code):
    # see whether there is a '.call(' in the line
    org_lines = code.split('\n')
    rtn = []
    empty_cnt = 0

    for line in org_lines:
        if line.find('.call(') > -1:
            # isolate arguments
            call_idx = line.find('.call(')
            fb_var_piece = line[:call_idx]
            words = fb_var_piece.split(' ')
            fb_var = words[-1]
            end_idx = line.find(')', call_idx+6)
            args = line[call_idx+6:end_idx]
            argList = args.split(',')
            extra_lines = []
            num_args = len(argList)
            for idx in reversed(range(0, num_args)):
                arg = argList[idx]
                arg_pieces = arg.split('=>')
                if len(arg_pieces) == 1:
                    continue

                fb_field = arg_pieces[0].strip()
                var_name = arg_pieces[1].strip()

                extra_lines.append(f"{var_name} = {fb_var}.{fb_field}")
                tail = copy.copy(argList[idx+1:])
                argList = argList[:idx]
                if len(tail) > 0:
                    argList.extend(tail)

            args_str = ','.join(argList)
            mod_line = f"{fb_var}.call({args_str})"
            rtn.append(mod_line)
            if len(extra_lines) > 0:
                rtn.extend(extra_lines)
        else:
            rtn.append(line)

    return '\n'.join(rtn)
 
def getArgs():
    global st_file, python_file, location_file, intrfc_file

    parser = argparse.ArgumentParser()
    parser.add_argument(u'-st', metavar = u'name of file with ST code',
                        dest=u'st_file', required=True)

    parser.add_argument(u'-intrfc', metavar = u'name of file with interface code',
                        dest=u'intrfc_file', required=True)

    if len(sys.argv) < 2:
        print("Useage ST2pyFB.py -st ST-File -intrfc interface-file")
        exit(1)

    args = parser.parse_args(sys.argv[1:])
    st_file = args.st_file
    intrfc_file = args.intrfc_file

    try:
        with open(st_file, 'r') as rf:
            x=1
    except:
        print(f"error: unable to open {st_file}")
        exit(1)

    try:
        with open(intrfc_file, 'r') as rf:
            x=1
    except:
        print(f"error: unable to open {st_file}")
        exit(1)

    file_path = Path(st_file).stem
    python_file   = file_path + '.py' 
    location_file = file_path + '.json'

def compute_mb_mapping():
    mb_idx = 0
    for subseq in IX_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += len(subseq.values)
        subseq.mb_last = mb_idx-1

    mb_idx = 0
    for subseq in IW_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += len(subseq.values)
        subseq.mb_last = mb_idx-1

    mb_idx = 0
    for subseq in QX_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += len(subseq.values)
        subseq.mb_last = mb_idx-1

    mb_idx = 0
    for subseq in QW_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += len(subseq.values)
        subseq.mb_last = mb_idx-1

    for subseq in MW_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += len(subseq.values)
        subseq.mb_last = mb_idx-1

    # make sure mb_idx is even
    mb_idx += mb_idx%2
    for subseq in MD_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += 2*len(subseq.values)
        subseq.mb_last = mb_idx-1

    # make sure mb_idx is multiple of 4 
    if mb_idx%4 > 0:
        mb_idx += (4-mb_idx%4)

    for subseq in ML_seq.subseq:
        subseq.mb_first = mb_idx
        mb_idx += 4*len(subseq.values)
        subseq.mb_last = mb_idx-1


def indent_python_code(python_code):
    # do alignment
    lines = python_code.split('\n')
    rtn = []
    indentStep = '    '
    indent = ''
    indentCnt = 0

    for line in lines:
        line = line.strip()
        if line.startswith('!@!START_BLK'):
            indentCnt += 1
            indentArray = [indentStep]*indentCnt
            indent = ''.join(indentArray)
            continue

        if line.startswith('!@!END_BLK'):
            if indentCnt > 0:
                indentCnt -= 1

            indentArray = [indentStep]*indentCnt
            indent = ''.join(indentArray)
            continue 

        line = indent+line
        rtn.append(line)

    return('\n'.join(rtn))


def strip_comments(blk):
    lines = blk.split('\n')
    rtn = []
    for line in lines:
        if line.find('(*') > -1 and line.find('*)') > -1:
            continue
        start = line.find('//')
        if start > -1:
            line = line[:start]
        rtn.append(line.strip())

    return '\n'.join(rtn)

def get_condition(clause):
    if clause.find('=')> -1 and clause.find('<=') == -1 and clause.find('>=') == -1:
        clause = clause.replace('=','==') 
    return clause.strip()
    

def trans_condition(pattern, code):
        matches = re.finditer(pattern, code, re.IGNORECASE | re.DOTALL)
        fill = []
        for test_clause in matches:
            # transform any '=' which is not part of '<=' or '>=' into '=='
            (srt,end) = test_clause.span()
            clause = code[srt:end+1]
            if clause.find('=')> -1 and clause.find('<=') == -1 and clause.find('>=') == -1:
                here = clause.find('=')
                fill.append(here+srt)

        for idx in reversed(range(0,len(fill))):
            here = fill[idx]
            code = code[:here]+'='+code[here:]

        return code

def old_find_instances(substr, mainstr, offset):
    locs = []
    start = 0
    while True:
        nxt_loc = mainstr.find(substr, start)
        if nxt_loc > -1:
            locs.append(nxt_loc+offset)
            start = nxt_loc+len(substr)
        else:
            break
    return locs

def find_instances(substr, mainstr, start_idx, end_idx=None): 
    locs = []
    start = start_idx

    if end_idx==None:
        end_idx = len(mainstr)

    while True:
        nxt_loc = mainstr.find(substr, start, end_idx)
        if nxt_loc > -1:
            locs.append(nxt_loc)
            start = nxt_loc+len(substr)
        else:
            break
    return locs




def add_loc_desc(subseq, var_inst):
    for idx in range(0,len(subseq.vards)):
        vard = subseq.vards[idx]
        name  = vard.name
        py_type = vard.py_type
        var_type = vard.var_type
        mem_code = vard.mem_code
        value = clean_value(subseq.values[idx])
        pos   = subseq.first+idx
        mb_idx = subseq.mb_first+idx
        var_dict = {'name':name, 'var_type': var_type, 'py_type': py_type, \
            'mem_code': mem_code, 'pos':pos, 'value':value, 'mb_idx': mb_idx}
        var_inst.append(var_dict)

def build_location_map(output_file):
    var_inst = []
    for subseq in IX_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in QX_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in IW_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in QW_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in MW_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in MD_seq.subseq:
        add_loc_desc(subseq, var_inst)

    for subseq in ML_seq.subseq:
        add_loc_desc(subseq, var_inst)

    with open(output_file,'w') as wf:
        json.dump(var_inst, wf, indent=2)

    # create a string representing var_inst and return it
    var_inst_str = json.dumps(var_inst)
    return var_inst_str

def mem_code_adv(mem_code, inc):
    pos = mem_code[2:] 
    if len(pos) == 0:
        return f"{mem_code[:2]}{inc}"

    pieces = pos.split('.')
    if len(pieces) == 1:
        pos = int(pos)+inc
        return f"{mem_code[:2]}{inc}"

    else:  
        word = int(pieces[0])
        bit  = int(pieces[1]) 
        pos = 8*word+bit+inc
       
        word = int(pos/8)
        bit  = pos%8
        return f"{mem_code[:2]}{word}.{bit}" 

add_st2py  = '\ndef plc_thread_function(spc):\n'
entry_call = '\nif __name__ == "__main__":\n    st2py()\n'
imports    = ('sys','os','pdb','json','copy','math','mbd','mbaux','threading','time')

def add_imports():
    rtn = []
    for module in imports:
        rtn.append(f"import {module}")
    return '\n'.join(rtn)+'\n'

def add_intrfc(intrfc_file):
    lines = []
    with open(intrfc_file,'r') as rf:
        for line in rf:
            line = line.replace('\n','')
            line = line.replace('\r','')
            lines.append(line) 

    rtn = '\n'.join(lines)
    return rtn+'\n'

def add_functions():
    return functions

def add_vars():
    return '\n'.join(global_lines)
    
if __name__ == "__main__":
    getArgs()

    convertor = ConvertorApp(st_file)
    python_code = convertor.convert()

    compute_mb_mapping()
    loc_map_str = build_location_map(location_file)

    loc_map_str = f"loc_map_str = '{loc_map_str}'\n"
    loc_map_str += "loc_map = json.loads(loc_map_str)\n\n" 

    python_code = python_code.replace('!@!START_MAIN','build_loc_map(loc_map)\nwhile True:\n!@!START_BLK\ntime.sleep(spc/1000)\ntop_of_cycle_import()\n')
    #python_code = add_imports()+'\n'+add_functions()+'\n'+add_vars()+add_st2py+'\n!@!START_BLK\n'+python_code+'\n!@!END_BLK\n'

    python_code = add_vars()+'\n'+loc_map_str+add_st2py+'!@!START_BLK\n'+global_stmnt+'\n!@!END_BLK\n'+python_code+'\nbottom_of_cycle_export()\n!@!END_BLK\n'
    python_code = fb_calls(python_code)
    python_code = indent_python_code(python_code)
    python_code = add_imports()+add_intrfc(intrfc_file)+'\n'+add_functions()+'\n'+python_code
    #python_code += entry_call
    python_code = convertor.clean_up_python_code(python_code)

    with open(python_file, 'w') as wf:
        wf.write(python_code) 

    
