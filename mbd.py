# data structures and code for the ST program to interact with the 
# cojoined Modbus server
#
# Modbus data block table variables
coilblock = None     
datablock = None     
inputRegblock = None
holdingRegblock = None

# given the data table, an address in that table, and a number of elements,
# acquire those values from the data table and return them, doing a conversion
# for tables holding booleans
#
def getTableValues(table, adrs, size):
    try:
        values = table.getValues(adrs, size)
        trns_values = []
        # is the table of interest representing boolean variables?
        if table==coilblock or table==datablock:
            # yes, so create explicit conversions
            for v in values:
                if isinstance(v,int):
                    vt = True if v%2 > 0 else False
                    trns_values.append(vt)
        else:
            trns_values = values
        return True, trns_values

    except:
        return False, []

# given the data table, an address in that table, and a list of values,
# write those values to the data table, doing a conversion
# for tables holding booleans
#
def setTableValues(table, adrs, values):
    try:
        trns_values = []
        # does this table manage Booleans?
        if table == coilblock or table==datablock:
            # yes, so do a conversion to integers 
            for v in values:
                if isinstance(v,bool):
                    vt = 1 if v else 0
                    trns_values.append(vt) 
        else:
            trns_values = values

        table.setValues(adrs, trns_values)
        return True
    except:
        return False


