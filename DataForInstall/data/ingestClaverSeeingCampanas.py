#!/usr/bin/env python
#
# cloned from F. Pierfederici's ingest_weather_data.py
#

import sys
import MySQLdb

# Database specific stuff
DBHOST = ''
DBDB = 'LSST'
DBTABLES = {'seeing': 'SeeingCampanas'}
DBUSER = 'www'
DBPASSWD = 'zxcvbnm'


def readFile(fileName, format=None):
    """
    Read the seeing data from fileName. In case of error accessing
    the file, an expection is raised of type IOError. If the file
    content is not valid, an expection of type SyntaxError is 
    raised.

    If fileName is None, None is returned; otherwise the file is 
    parsed (using the information in format) and a hash table, 
    whose key is date and whose value is an arrays of (seeing), is returned.

    Format (input)
    The format of the input file (fileName) is specified in the
    format parameter. format is the python code that will be used
    to parse each space splitted line. It has to export the two
    variables (date, cloud). It imports an array of elements called cols. 
    It can assume that the output hash table has already been initialized.

    Format/units (output)
    date    %d (MJD in seconds)
    seeing  %.02f

    *** THIS METHOD WILL MIGRATE IN A STAND-ALONE EXECUTABLE ***
    """
    try:
        lines = file(fileName).readlines()
    except:
        raise (IOError,
               'error in opening input file (%s)' % (fileName))
        return (None)

    # Open a database connection
    conn = MySQLdb.connect(user=DBUSER,
                           passwd=DBPASSWD,
                           db=DBDB,
                           host=DBHOST)

    # Acquire a cursor
    cur = conn.cursor()

    # Print some status
    tot = len(lines)
    print ('Preparing to process %d entries...' % (tot))

    # MySQL does not necessarily support transactions!
    i = 0           # number of valid lines
    j = 0           # number of invalid/empty lines
    for line in lines:
        cols = line.split()
        if (cols):
            sql = 'INSERT INTO %s VALUES \n' % (DBTABLES['seeing'])
            try:
                # <FORMAT>
                time = float(cols[0])
                seeing = float(cols[1])
                # </FORMAT>

                i += 1

                # ingest the values in the database
                sql += '(%d, %f);' % (int(time), seeing)
            except:
                j += 1
                print ('error in line "%s"' % (line))
                raise (SyntaxError, 'error in %s' % (line))
            # Send the SQL to the database
            n = cur.execute(sql)
        else:
            j += 1
            print ('skipping line "%s"' % (line))
    # <-- end for

    print ('Processed %d/%d entries, skipped %d/%d lines.' % (i, tot, j, tot))

    # Close the connection to the DB
    del (cur)
    del (conn)
    return


if (__name__ == '__main__'):
    readFile(sys.argv[1])
