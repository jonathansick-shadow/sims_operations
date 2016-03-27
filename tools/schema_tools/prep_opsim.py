import os

import MySQLdb as mysqldb


def connect_db(hostname='localhost', username='www', passwdname='zxcvbnm', dbname='LSST'):
    # connect to lsst_pointings (or other) mysql db, using account that has 'alter table' privileges
    # connect to the database - this is modular to allow for easier modification from machine/machine
    db = None
    conf_file = os.path.join(os.getenv("HOME"), ".my.cnf")
    if os.path.isfile(conf_file):
        db = mysqldb.connect(read_default_file=conf_file, db=dbname)
    else:
        db = mysqldb.connect(host=hostname, user=username, passwd=passwdname, db=dbname)
    cursor = db.cursor()
    return cursor


def add_indexes(database, simname):
    # adds some useful indexes for calculating values from opsim
    # set up a dictionary to hold the index info
    index_done = {}
    indexlist = ("fieldID", "expMJD", "filter", "fieldRA", "fieldDec", "fieldRADec", "night")
    for ind in indexlist:
        index_done[ind] = False
    # connect to the db
    cursor = connect_db(dbname=database)
    # check for existing indexes
    sqlquery = "show indexes from %s" % (simname)
    cursor.execute(sqlquery)
    results = cursor.fetchall()
    # do some testing to see if index (solely on this item) exists
    for result in results:
        if (result[3] == 1):   # this is a first part of an index
            if result[4] in index_done.keys():  # is this index one of the ones we're looking for?
                index_done[result[4]] = True
        # fieldRA and dec more complicated, as secondary (both) index too
        elif (result[3] == 2):
            if result[4] == "fieldDec":
                index_done["fieldRADec"] = True
    print index_done
    for ind in indexlist:
        if (index_done[ind]):
            print "Already have an index on %s - skipping" % (ind)
        else:
            print "Adding index for %s" % (ind)
            sqlquery = "create index %s_idx on %s(%s)" % (ind, simname, ind)
            if ind == 'fieldRADec':
                sqlquery = "create index %s_idx on %s(fieldRA, fieldDec)" % (ind, simname)
            print sqlquery
            cursor.execute(sqlquery)
    # general format for index is columnname_idx
    # will create night index when add night information
    # also will add hexdith* indexes when add dither information
    print "Done adding indexes"
    cursor.close()


def remove_dither(simname, dropdatacol = False):
    print "Removing existing dithering indexes and columns."
    cursor = connect_db()
    sqlquery = "drop index ditheredRA_idx on %s" % (simname)
    cursor.execute(sqlquery)
    sqlquery = "drop index ditheredDec_idx on %s" % (simname)
    cursor.execute(sqlquery)
    sqlquery = "drop index ditheredRADec_idx on %s" % (simname)
    cursor.execute(sqlquery)
    if dropdatacol:
        print "Removed indexes - now will remove columns ditheredRA/dec."
        sqlquery = "alter table %s drop column ditheredRA, drop column ditheredDec" % (simname)
        cursor.execute(sqlquery)
    cursor.close()
    return


def offsetHex():
    import numpy
    # some constants for the dithering
    fov = 3.5
    # set values associated with dithering
    dith_level = 4
    # number of rows in dither pattern
    # number of vertices in longest row is the same.
    nrows = 2**dith_level
    halfrows = int(nrows/2)  # useful for counting from 0 at center
    # calculate size of each offset
    dith_size_x = fov / (nrows)
    dith_size_y = numpy.sqrt(3) * fov/2.0/(nrows)  # sqrt 3 comes from hexagon
    # calculate the row identification number, going from 0 at center
    nid_row = numpy.arange(-halfrows, halfrows+1, 1)
    # and calculate the number of vertices in each row
    vert_in_row = numpy.arange(-halfrows, halfrows+1, 1)
    total_vert = 0
    offsets = []
    for i in range(-halfrows, halfrows+1, 1):
        vert_in_row[i] = (nrows+1) - abs(nid_row[i])
        total_vert += vert_in_row[i]
    vertex_count = 0
    for i in range(0, nrows+1, 1):
        for j in range(0, vert_in_row[i], 1):
            # calculate displacement
            x_off = numpy.radians(dith_size_x * (j - (vert_in_row[i]-1)/2.0))
            y_off = numpy.radians(dith_size_y * nid_row[i])
            offsets.append([x_off, y_off])
            vertex_count += 1
    return offsets


def add_dither(database, simname, overwrite=True):
    # Add the Krughoff-Jones dithering pattern to the opsim output
    # adds three columns (ditheredRA, ditheredDec, and vertex) and indexes
    # connect to the database
    cursor = connect_db(dbname=database)
    # check if dithering columns exist
    sqlquery = "describe %s"%(simname)
    cursor.execute(sqlquery)
    newcols = ['ditheredRA', 'ditheredDec']
    sqlresults = cursor.fetchall()
    for result in sqlresults:
        if (result[0] == 'ditheredRA' or result[0] == 'ditheredDec'):
            newcols.remove(result[0])
            if overwrite:
                print '%s column already exists, but will overwrite.' % (result[0])
            if overwrite == False:
                print "%s column already exists - skipping adding dithering" % (result[0])
                break
    if len(newcols) > 0:
        print 'Adding dithering columns'
        for n in newcols:
            # add columns for dithering
            sqlquery = 'alter table %s add %s double' % (simname, n)
            cursor.execute(sqlquery)
    # want to change vertex on night/night basis, so pull all night values from db
    sqlquery = "select distinct(night) from %s"%(simname)
    # print sqlquery
    cursor.execute(sqlquery)
    sqlresults = cursor.fetchall()
    # go through each night individually
    offsets = offsetHex()
    for result in sqlresults:
        night = int(result[0])
        vertex = night%len(offsets)
        x_off, y_off = offsets[vertex]
        # It doesn't make a ton of sense, but see http://bugs.mysql.com/bug.php?id=1665 for a discussion of the mysql modulus convention.
        # In the case where a mod can return a negative value (((N%M)+M)%M) will return what one would expect.
        sqlquery = "update %s set ditheredRA = ((((fieldra+(%f/cos(fielddec)))%%(2*PI()))+(2*PI()))%%(2*PI())), ditheredDec = if(abs(fielddec + %f) > 90, fielddec  - %f, fielddec + %f) where night = %i"%(
            simname, x_off, y_off, y_off, y_off, night)
        # Sometimes when the offset is 0 the above may still produce dec centers < -90 deg because fielddec can be < -pi/2. because of rounding issues.
        # it would make for a very complicated query string.
        cursor.execute(sqlquery)
        # print "Night %d done ....:" % (night)
    # This shouldn't really happen, but if outside -PI/2 -- PI/2 reflect to
    # the proper bounds.  This does happen sometimes due to rounding issues.
    sqlquery = "update %s set ditheredDec = -PI()/2. - (((ditheredDec%%(-PI()/2)) + (-PI()/2.))%%(-PI()/2.)) where ditheredDec < -PI()/2;"%(simname)
    cursor.execute(sqlquery)
    sqlquery = "update %s set ditheredDec = PI()/2. - (((ditheredDec%%(PI()/2)) + (PI()/2.))%%(PI()/2.)) where ditheredDec > PI()/2;"%(simname)
    cursor.execute(sqlquery)
    # add indexes
    print "Adding dithering indexes"
    sqlquery = "create index ditheredRA_idx on %s(ditheredRA)" % (simname)
    cursor.execute(sqlquery)
    sqlquery = "create index ditheredDec_idx on %s(ditheredDec)" % (simname)
    cursor.execute(sqlquery)
    sqlquery = "create index ditheredRADec_idx on %s(ditheredRA, ditheredDec)" % (simname)
    cursor.execute(sqlquery)
    cursor.close()

if __name__ == "__main__":

    # Give this the opsim name, then will update opsim to add useful information & indexes

    import sys

    if len(sys.argv) < 3:
        print "Usage : './prep_opsim.py <realhostname> <databasename> <sessionID>'"
        sys.exit(1)
    hname = sys.argv[1]
    database = sys.argv[2]
    sessionID = sys.argv[3]
    opsimname = "summary_" + hname + "_" + sessionID
    # print "Updating %s" %(opsimname)
    add_indexes(database, opsimname)
    add_dither(database, opsimname, overwrite=False)
