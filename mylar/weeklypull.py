#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.


from __future__ import print_function

import sys 
import fileinput 
import csv 
import getopt 
import sqlite3 
import urllib 
import os 
import time 
import re
import datetime

import mylar 
from mylar import db, updater, helpers, logger

def pullit(forcecheck=None):
    myDB = db.DBConnection()
    popit = myDB.select("SELECT count(*) FROM sqlite_master WHERE name='weekly' and type='table'")
    if popit:
        try:
            pull_date = myDB.action("SELECT SHIPDATE from weekly").fetchone()
            logger.info(u"Weekly pull list present - checking if it's up-to-date..")
            if (pull_date is None):
                pulldate = '00000000'
            else:
                pulldate = pull_date['SHIPDATE']
        except (sqlite3.OperationalError, TypeError),msg:
            conn=sqlite3.connect(mylar.DB_FILE)
            c=conn.cursor()
            logger.info(u"Error Retrieving weekly pull list - attempting to adjust")
            c.execute('DROP TABLE weekly')    
            c.execute('CREATE TABLE IF NOT EXISTS weekly (SHIPDATE text, PUBLISHER text, ISSUE text, COMIC VARCHAR(150), EXTRA text, STATUS text, ComicID text)')
            pulldate = '00000000'
            logger.fdebug(u"Table re-created, trying to populate")
    else:
        logger.info(u"No pullist found...I'm going to try and get a new list now.")
        pulldate = '00000000'
    if pulldate is None: pulldate = '00000000'
    PULLURL = 'http://www.previewsworld.com/shipping/newreleases.txt'
    #PULLURL = 'http://www.previewsworld.com/Archive/GetFile/1/1/71/994/081512.txt'

    #Prepare the Substitute name switch for pulllist to comic vine conversion
    substitutes = os.path.join(mylar.DATA_DIR,"substitutes.csv")
    if not os.path.exists(substitutes):
        logger.debug('no substitues.csv file located - not performing substitutions on weekly pull list')
        substitute_check = False
    else:
        substitute_check = True
        #shortrep is the name to be replaced, longrep the replacement
        shortrep=[]
        longrep=[]
        #open the file data
        with open(substitutes) as f:
            reader = csv.reader(f, delimiter='|')
            for row in reader:
                if not row[0].startswith('#'): 
                    logger.fdebug("Substitutes file read : "+str(row))
                    shortrep.append(row[0])
                    longrep.append(row[1])
        f.close()

    not_these=['PREVIEWS',
               'Shipping',
               'Every Wednesday',
               'Please check with',
               'PREMIER PUBLISHERS',
               'BOOKS',
               'COLLECTIBLES',
               'MCFARLANE TOYS',
               'New Releases',
               'Upcoming Releases']

    excludes=['2ND PTG',
              '3RD PTG',
              '4TH PTG',
              '5TH PTG',
              'NEW PTG',
              'POSTER',
              'COMBO PACK']

    # this checks for the following lists
    # first need to only look for checkit variables
    checkit=['COMICS',
             'COMIC & GRAPHIC NOVELS',
             'IDW PUBLISHING',
             'MAGAZINES',
             'MERCHANDISE']

    #if COMICS is found, determine which publisher
    checkit2=['DC',
              'MARVEL',
              'DARK HORSE',
              'IMAGE']
    # used to determine type of comic (one shot, hardcover, tradeback, softcover, graphic novel)
    cmty=['HC',
          'TP',
          'GN',
          'SC',
          'ONE SHOT',
          'PI']

    pub = "COMICS"
    prevcomic = ""
    previssue = ""

    #newtxtfile header info ("SHIPDATE\tPUBLISHER\tISSUE\tCOMIC\tEXTRA\tSTATUS\n")
    #STATUS denotes default status to be applied to pulllist in Mylar (default = Skipped)
    newrl = mylar.CACHE_DIR + "/newreleases.txt"
    f = urllib.urlretrieve(PULLURL, newrl)
#    local_file = open(newrl, "wb")
#    local_file.write(f.read())
#    local_file.close

    newfl = mylar.CACHE_DIR + "/Clean-newreleases.txt"
    newtxtfile = open(newfl, 'wb')

    if check(newrl, 'Service Unavailable'):
        logger.info('Retrieval site is offline at the moment.Aborting pull-list update amd will try again later.')
        pullitcheck(forcecheck=forcecheck)
    else:
        pass

    for i in open(newrl):
        if not i.strip():
            continue
        if 'MAGAZINES' in i: break
        if 'MERCHANDISE' in i: break
        for nono in not_these:
            if nono in i:
                #let's try and grab the date for future pull checks
                if i.startswith('Shipping') or i.startswith('New Releases') or i.startswith('Upcoming Releases'):
                    shipdatechk = i.split()
                    if i.startswith('Shipping'):
                        shipdate = shipdatechk[1]                
                    elif i.startswith('New Releases'):
                        shipdate = shipdatechk[3]
                    elif i.startswith('Upcoming Releases'):
                        shipdate = shipdatechk[3]
                    sdsplit = shipdate.split('/')
                    mo = sdsplit[0]
                    dy = sdsplit[1]
                    if len(mo) == 1: mo = "0" + sdsplit[0]
                    if len(dy) == 1: dy = "0" + sdsplit[1]
                    shipdate = sdsplit[2] + "-" + mo + "-" + dy
                    shipdaterep = shipdate.replace('-', '')
                    pulldate = re.sub('-', '', str(pulldate))
                    #print ("shipdate: " + str(shipdaterep))
                    #print ("today: " + str(pulldate))
                    if pulldate == shipdaterep:
                        logger.info(u"No new pull-list available - will re-check again in 24 hours.")
                        pullitcheck()
                        mylar.PULLNEW = 'no'
                        return
                    else:
                        logger.info(u"Preparing to update to the new listing.")
                break    
        else:
            mylar.PULLNEW = 'yes'
            for yesyes in checkit:
                if yesyes in i:
                    if format(str(yesyes)) == 'COMICS':
                        for chkchk in checkit2:
                            flagged = "no"
                            if chkchk in i:
                                bl = i.split()
                                blchk = str(bl[0]) + " " + str(bl[1])
                                if chkchk in blchk:
                                    pub = format(str(chkchk)) + " COMICS"
                                    #print (pub)
                                    break
                            else:
                                if i.find("COMICS") < 1 and "GRAPHIC NOVELS" in i:
                                    pub = "COMICS"
                                    #print (pub)
                                    break 
                                elif i.find("COMICS") > 12:
                                    #print ("comics word found in comic title")
                                    flagged = "yes"                    
                                    break
                    else:
                        if i.find("COMIC") < 1 and "GRAPHIC NOVELS" in i:
                            pub = "COMICS"
                            break
                        else:
                            pub = format(str(yesyes))
                            #print (pub)
                            break
                    if flagged == "no": 
                        break
            else:
                dupefound = "no"
                if '#' in i:
                    issname = i.split()
                    #print (issname)
                    issnamec = len(issname)
                    n = 0
                    while (n < issnamec):
                        #find the issue
                        if '#' in (issname[n]):
                            if issname[n] == "PI":
                                issue = "NA"
                                break
                            issue = issname[n]
                            if 'ongoing' not in issname[n-1].lower() and '(vu)' not in issname[n-1].lower():
                                #print ("issue found : " + issname[n])
                                comicend = n - 1
                            else:
                                comicend = n - 2
                            break
                        n+=1
                    if issue == "": issue = 'NA'
                    #find comicname
                    comicnm = issname[1]
                    n = 2
                    while (n < comicend + 1):
                        comicnm = comicnm + " " + issname[n]
                        n+=1
                    #print ("Comicname: " + str(comicnm) )
                    #get remainder
                    comicrm = issname[comicend +2]
                    if '$' in comicrm:
                        comicrm="None"
                    n = (comicend + 3)
                    while (n < issnamec):
                        if '$' in (issname[n]):
                            break
                        comicrm = str(comicrm) + " " + str(issname[n])
                        n+=1
                    #print ("Comic Extra info: " + str(comicrm) )
                    #print ("ship: " + str(shipdate))
                    #print ("pub: " + str(pub))
                    #print ("issue: " + str(issue))
                    #--let's make sure we don't wipe out decimal issues ;)
#                    if '.' in issue:
#                        issue_decimal = re.compile(r'[^\d.]+')
#                        issue = issue_decimal.sub('', str(issue))
#                    else: issue = re.sub('#','', issue)                                       
                    issue = re.sub('#','', issue)
                    #issue = re.sub("\D", "", str(issue))
                    #store the previous comic/issue for comparison to filter out duplicate issues/alt covers
                    #print ("Previous Comic & Issue: " + str(prevcomic) + "--" + str(previssue))
                    dupefound = "no"
                else:
                    #if it doesn't have a '#' in the line, then we know it's either
                    #a special edition of some kind, or a non-comic
                    issname = i.split()
                    #print (issname)
                    issnamec = len(issname)
                    n = 1
                    issue = ''
                    while (n < issnamec):
                        #find the type of non-issue (TP,HC,GN,SC,OS,PI etc)
                        for cm in cmty:
                            if "ONE" in issue and "SHOT" in issname[n+1]: issue = "OS"
                            if cm == (issname[n]):
                                if issname[n] == 'PI':
                                    issue = 'NA'
                                    break
                                issue = issname[n]
                                #print ("non-issue found : " + issue)
                                comicend = n - 1
                                break
                        n+=1
                    #if the comic doesn't have an issue # or a keyword, adjust.
                    #set it to 'NA' and it'll be filtered out anyways.
                    if issue == "" or issue is None:
                        issue = 'NA'
                        comicend = n - 1  #comicend = comicend - 1  (adjustment for nil)
                    #find comicname
                    comicnm = issname[1]
                    n = 2
                    while (n < comicend + 1):
                        #stupid - this errors out if the array mistakingly goes to far.
                        try:
                            comicnm = comicnm + " " + issname[n]
                        except IndexError:
                            #print ("went too far looking at this comic...adjusting.")
                            comicnm = comicnm
                            break
                        n+=1
                    #print ("Comicname: " + str(comicnm) )
                    #get remainder
                    if len(issname) <= (comicend + 2):
                        comicrm = "None"
                    else:
                        #print ("length:" + str(len(issname)))
                        #print ("end:" + str(comicend + 2))
                        comicrm = issname[comicend +2]
                    if '$' in comicrm:
                        comicrm="None"
                    n = (comicend + 3)
                    while (n < issnamec):
                        if '$' in (issname[n]) or 'PI' in (issname[n]):
                            break
                        comicrm = str(comicrm) + " " + str(issname[n])
                        n+=1
                    #print ("Comic Extra info: " + str(comicrm) )
                    if "NA" not in issue and issue != "":
                        #print ("shipdate:" + str(shipdate))
                        #print ("pub: " + str(pub))
                        #print ("issue: " + str(issue))
                        dupefound = "no"
                #--start duplicate comic / issue chk
                # pullist has shortforms of a series' title sometimes and causes problems
                if 'O/T' in comicnm:
                    comicnm = re.sub('O/T', 'OF THE', comicnm)

                if substitute_check == True:
                    #Step through the list - storing an index
                    for repindex,repcheck in enumerate(shortrep):
                        if len(comicnm) >= len(repcheck):
                            #if the leftmost chars match the short text then replace them with the long text
                            if comicnm[:len(repcheck)]==repcheck:
                                logger.info("Switch worked on "+comicnm + " replacing " + str(repcheck) + " with " + str(longrep[repindex]))
                                comicnm = re.sub(repcheck, longrep[repindex], comicnm)

                for excl in excludes:
                    if excl in str(comicrm):
                        #duplicate comic / issue detected - don't add...
                        dupefound = "yes"
                if prevcomic == str(comicnm) and previssue == str(issue):
                    #duplicate comic/issue detected - don't add...
                    dupefound = "yes"
                #--end duplicate chk
                if (dupefound != "yes") and ('NA' not in str(issue)):
                    newtxtfile.write(str(shipdate) + '\t' + str(pub) + '\t' + str(issue) + '\t' + str(comicnm) + '\t' + str(comicrm) + '\tSkipped' + '\n')
                prevcomic = str(comicnm)
                previssue = str(issue)
    logger.info(u"Populating the NEW Weekly Pull list into Mylar.")
    newtxtfile.close()

    mylardb = os.path.join(mylar.DATA_DIR, "mylar.db")

    connection = sqlite3.connect(str(mylardb))
    cursor = connection.cursor()

    cursor.executescript('drop table if exists weekly;')

    cursor.execute("CREATE TABLE IF NOT EXISTS weekly (SHIPDATE, PUBLISHER text, ISSUE text, COMIC VARCHAR(150), EXTRA text, STATUS text, ComicID text);")
    connection.commit()


    csvfile = open(newfl, "rb")
    creader = csv.reader(csvfile, delimiter='\t')
    t=1

    for row in creader:
        if "MERCHANDISE" in row: break
        if "MAGAZINES" in row: break
        if "BOOK" in row: break
        #print (row)
        try:
            logger.debug("Row: %s" % row)
            cursor.execute("INSERT INTO weekly VALUES (?,?,?,?,?,?,null);", row)
        except Exception, e:
            #print ("Error - invald arguments...-skipping")
            pass
        t+=1
    csvfile.close()
    connection.commit()
    connection.close()
    logger.info(u"Weekly Pull List successfully loaded.")
    #let's delete the files
    pullpath = str(mylar.CACHE_DIR) + "/"
    os.remove( str(pullpath) + "Clean-newreleases.txt" )
    os.remove( str(pullpath) + "newreleases.txt" )
    pullitcheck(forcecheck=forcecheck)

def pullitcheck(comic1off_name=None,comic1off_id=None,forcecheck=None, futurepull=None, issue=None):
    if futurepull is None:
        logger.info(u"Checking the Weekly Releases list for comics I'm watching...")
    else:
        logger.info('Checking the Future Releases list for upcoming comics I am watching for...')
    myDB = db.DBConnection()

    not_t = ['TP',
             'NA',
             'HC',
             'PI']

    not_c = ['PTG',
             'COMBO PACK',
             '(PP #']

    lines = []
    unlines = []
    llen = []
    ccname = []
    pubdate = []
    latestissue = []
    w = 0
    wc = 0
    tot = 0
    chkout = []
    watchfnd = []
    watchfndiss = []
    watchfndextra = []
    alternate = []

    #print ("----------WATCHLIST--------")
    a_list = []
    b_list = []
    comicid = []

    mylardb = os.path.join(mylar.DATA_DIR, "mylar.db")

    con = sqlite3.connect(str(mylardb))

    with con:

        cur = con.cursor()
        # if it's a one-off check (during an add series), load the comicname here and ignore below.
        if comic1off_name:
            logger.fdebug("this is a one-off" + comic1off_name)
            lines.append(comic1off_name.strip())
            unlines.append(comic1off_name.strip())
            comicid.append(comic1off_id)
            latestissue.append(issue)
            w = 1            
        else:
            #let's read in the comic.watchlist from the db here
            cur.execute("SELECT ComicID, ComicName, ComicYear, ComicPublisher, ComicPublished, LatestDate, ForceContinuing, AlternateSearch, LatestIssue from comics")
            while True:
                watchd = cur.fetchone()
                #print ("watchd: " + str(watchd))
                if watchd is None:
                    break
                if 'Present' in watchd[4] or (helpers.now()[:4] in watchd[4]) or watchd[6] == 1:
                 # this gets buggered up when series are named the same, and one ends in the current
                 # year, and the new series starts in the same year - ie. Avengers
                 # lets' grab the latest issue date and see how far it is from current
                 # anything > 45 days we'll assume it's a false match ;)
                    logger.fdebug("ComicName: " + watchd[1])
                    latestdate = watchd[5]
                    logger.fdebug("latestdate:  " + str(latestdate))
                    if latestdate[8:] == '':
                        logger.fdebug("invalid date " + str(latestdate) + " appending 01 for day for continuation.")
                        latest_day = '01'
                    else:
                        latest_day = latestdate[8:]
                    c_date = datetime.date(int(latestdate[:4]),int(latestdate[5:7]),int(latest_day))
                    n_date = datetime.date.today()
                    logger.fdebug("c_date : " + str(c_date) + " ... n_date : " + str(n_date))
                    recentchk = (n_date - c_date).days
                    logger.fdebug("recentchk: " + str(recentchk) + " days")
                    chklimit = helpers.checkthepub(watchd[0])
                    logger.fdebug("Check date limit set to : " + str(chklimit))
                    logger.fdebug(" ----- ")
                    if recentchk < int(chklimit) or watchd[6] == 1:
                        if watchd[6] == 1:
                            logger.fdebug('Forcing Continuing Series enabled for series...')
                        # let's not even bother with comics that are not in the Present.
                        a_list.append(watchd[1])
                        b_list.append(watchd[2])
                        comicid.append(watchd[0])
                        pubdate.append(watchd[4])
                        latestissue.append(watchd[8])
                        lines.append(a_list[w].strip())
                        unlines.append(a_list[w].strip())
                        w+=1   # we need to increment the count here, so we don't count the same comics twice (albeit with alternate names)

                        #here we load in the alternate search names for a series and assign them the comicid and
                        #alternate names
                        Altload = helpers.LoadAlternateSearchNames(watchd[7], watchd[0])
                        if Altload == 'no results':
                            pass
                        else:
                            wc = 0 
                            alt_cid = Altload['ComicID']
                            n = 0
                            iscnt = Altload['Count']
                            while (n <= iscnt):
                                try:
                                    altval = Altload['AlternateName'][n]
                                except IndexError:
                                    break
                                cleanedname = altval['AlternateName']
                                a_list.append(altval['AlternateName'])
                                b_list.append(watchd[2])
                                comicid.append(alt_cid)
                                pubdate.append(watchd[4])
                                latestissue.append(watchd[8])
                                lines.append(a_list[w+wc].strip())
                                unlines.append(a_list[w+wc].strip())
                                logger.fdebug('loading in Alternate name for ' + str(cleanedname))
                                n+=1
                                wc+=1
                            w+=wc

                #-- to be removed - 
                        #print ( "Comic:" + str(a_list[w]) + " Year: " + str(b_list[w]) )
                        #if "WOLVERINE AND THE X-MEN" in str(a_list[w]): a_list[w] = "WOLVERINE AND X-MEN"
                        #lines.append(a_list[w].strip())
                        #unlines.append(a_list[w].strip())
                        #llen.append(a_list[w].splitlines())
                        #ccname.append(a_list[w].strip())
                        #tmpwords = a_list[w].split(None)
                        #ltmpwords = len(tmpwords)
                        #ltmp = 1
                #-- end to be removed
                    else:
                        logger.fdebug("Determined to not be a Continuing series at this time.")    
        cnt = int(w-1)
        cntback = int(w-1)
        kp = []
        ki = []
        kc = []
        otot = 0

        logger.fdebug("You are watching for: " + str(w) + " comics")
        #print ("----------THIS WEEK'S PUBLISHED COMICS------------")
        if w > 0:
            while (cnt > -1):
                latestiss = latestissue[cnt]
                lines[cnt] = lines[cnt].upper()
                #llen[cnt] = str(llen[cnt])
                logger.fdebug("looking for : " + lines[cnt])
                sqlsearch = re.sub('[\_\#\,\/\:\;\.\-\!\$\%\'\?\@]', ' ', lines[cnt])
                sqlsearch = re.sub("\&", '%', sqlsearch)
                sqlsearch = re.sub("\\bAND\\b", '%', sqlsearch)
                sqlsearch = re.sub("\\bTHE\\b", '', sqlsearch)
                if '+' in sqlsearch: sqlsearch = re.sub('\+', '%PLUS%', sqlsearch)
                sqlsearch = re.sub(r'\s', '%', sqlsearch)
                sqlsearch = sqlsearch + '%'
                #logger.fdebug("searchsql: " + sqlsearch)
                if futurepull is None:
                    weekly = myDB.select('SELECT PUBLISHER, ISSUE, COMIC, EXTRA, SHIPDATE FROM weekly WHERE COMIC LIKE (?)', [sqlsearch])
                else:
                    weekly = myDB.select('SELECT PUBLISHER, ISSUE, COMIC, EXTRA, SHIPDATE FROM future WHERE COMIC LIKE (?)', [sqlsearch])
                #cur.execute('SELECT PUBLISHER, ISSUE, COMIC, EXTRA, SHIPDATE FROM weekly WHERE COMIC LIKE (?)', [lines[cnt]])
                for week in weekly:
                    if week == None:
                        break
                    for nono in not_t:
                        if nono in week['PUBLISHER']:
                            #logger.fdebug("nono present")
                            break
                        if nono in week['ISSUE']:
                            #logger.fdebug("graphic novel/tradeback detected..ignoring.")
                            break
                        for nothere in not_c:
                            if nothere in week['EXTRA']:
                                #logger.fdebug("nothere present")
                                break
                            else:
                                comicnm = week['COMIC']
                                #here's the tricky part, ie. BATMAN will match on
                                #every batman comic, not exact
                                logger.fdebug("comparing" + comicnm + "..to.." + unlines[cnt].upper())

                                #-NEW-
                                # strip out all special characters and compare
                                watchcomic = re.sub('[\_\#\,\/\:\;\.\-\!\$\%\'\?\@]', '', unlines[cnt])
                                comicnm = re.sub('[\_\#\,\/\:\;\.\-\!\$\%\'\?\@]', '', comicnm)
                                if "THE" in watchcomic.upper() or "THE" in comicnm.upper():
                                    modwatchcomic = re.sub("\\bTHE\\b", "", watchcomic.upper())
                                    modcomicnm = re.sub("\\bTHE\\b", "", comicnm)
                                else:
                                    modwatchcomic = watchcomic
                                    modcomicnm = comicnm
                                if '&' in watchcomic.upper():
                                    modwatchcomic = re.sub('\&', 'AND', modwatchcomic.upper())
                                    modcomicnm = re.sub('\&', 'AND', modcomicnm)
                                if '&' in comicnm:
                                    modwatchcom = re.sub('\&', 'AND', modwatchcomic.upper())
                                    modcomicnm = re.sub('\&', 'AND', modcomicnm)
                                #thnx to A+X for this...
                                if '+' in watchcomic:
                                    logger.fdebug("+ detected...adjusting.")
                                    #logger.fdebug("comicnm:" + comicnm)
                                    #logger.fdebug("watchcomic:" + watchcomic)
                                    modwatchcomic = re.sub('\+', 'PLUS', modwatchcomic)
                                    #logger.fdebug("modcomicnm:" + modcomicnm)
                                    #logger.fdebug("modwatchcomic:" + modwatchcomic)

                                #annuals!
                                if 'ANNUAL' in comicnm.upper(): 
                                    modcomicnm = re.sub("\\bANNUAL\\b", "", modcomicnm.upper())

                                watchcomic = re.sub(r'\s', '', watchcomic)
                                comicnm = re.sub(r'\s', '', comicnm)
                                modwatchcomic = re.sub(r'\s', '', modwatchcomic)
                                modcomicnm = re.sub(r'\s', '', modcomicnm)
                                logger.fdebug("watchcomic : " + str(watchcomic) + " / mod :" + str(modwatchcomic))
                                logger.fdebug("comicnm : " + str(comicnm) + " / mod :" + str(modcomicnm))

                                if comicnm == watchcomic.upper() or modcomicnm == modwatchcomic.upper():
                                    logger.fdebug("matched on:" + comicnm + "..." + watchcomic.upper())
                                    pass
#                                elif ("ANNUAL" in week['EXTRA']):
#                                    pass
#                                    print ( row[3] + " matched on ANNUAL")
                                else:
                                    break


                                if ("NA" not in week['ISSUE']) and ("HC" not in week['ISSUE']):
                                    if ("COMBO PACK" not in week['EXTRA']) and ("2ND PTG" not in week['EXTRA']) and ("3RD PTG" not in week['EXTRA']):

                                    #this all needs to get redone, so the ability to compare issue dates can be done systematically.
                                    #Everything below should be in it's own function - at least the callable sections - in doing so, we can
                                    #then do comparisons when two titles of the same name exist and are by definition 'current'. Issue date comparisons
                                    #would identify the difference between two #1 titles within the same series year, but have different publishing dates.
                                    #Wolverine (2013) & Wolverine (2014) are good examples of this situation.
                                    #of course initially, the issue data for the newer series wouldn't have any issue data associated with it so it would be
                                    #a null value, but given that the 2013 series (as an example) would be from 2013-05-01, it obviously wouldn't be a match to
                                    #the current date & year (2014). Throwing out that, we could just assume that the 2014 would match the #1.

                                    #get the issue number of the 'weeklypull' series.
                                    #load in the actual series issue number's store-date (not publishing date)
                                    #---use a function to check db, then return the results in a tuple/list to avoid db locks.
                                    #if the store-date is >= weeklypull-list date then continue processing below.
                                    #if the store-date is <= weeklypull-list date then break.
                                    ### week['ISSUE']  #issue # from pullist
                                    ### week['SHIPDATE']  #weeklypull-list date
                                    ### comicid[cnt] #comicid of matched series                                                                

                                    ## if it's a futurepull, the dates get mixed up when two titles exist of the same name
                                    ## ie. Wolverine-2011 & Wolverine-2014
                                    ## we need to set the compare date to today's date ( Now() ) in this case.
                                        if futurepull:
                                            usedate = datetime.datetime.now().strftime('%Y%m%d')  #convert to yyyymmdd
                                        else:
                                            usedate = re.sub("[^0-9]", "", week['SHIPDATE'])

                                        if 'ANNUAL' in comicnm.upper():
                                            chktype = 'annual'
                                        else:
                                            chktype = 'series' 
                             
                                        datevalues = loaditup(watchcomic, comicid[cnt], week['ISSUE'], chktype)

                                        date_downloaded = None
                                        altissuenum = None

                                        if datevalues == 'no results':
                                        #if a series is a .NOW on the pullist, it won't match up against anything (probably) on CV
                                        #let's grab the digit from the .NOW, poll it against CV to see if there's any data
                                        #if there is, check the store date to make sure it's a 'new' release.
                                        #if it is a new release that has the same store date as the .NOW, then we assume
                                        #it's the same, and assign it the AltIssueNumber to do extra searches.
                                            if week['ISSUE'].isdigit() == False and '.' not in week['ISSUE']:
                                                altissuenum = re.sub("[^0-9]", "", week['ISSUE'])  # carry this through to get added to db later if matches
                                                logger.fdebug('altissuenum is: ' + str(altissuenum))
                                                altvalues = loaditup(watchcomic, comicid[cnt], altissuenum, chktype)
                                                if altvalues == 'no results':
                                                    logger.fdebug('No alternate Issue numbering - something is probably wrong somewhere.')
                                                    pass

                                                validcheck = checkthis(altvalues[0]['issuedate'], altvalues[0]['status'], usedate)
                                                if validcheck == False:
                                                    if date_downloaded is None:
                                                        break
                                            if chktype == 'series': 
                                                latest_int = helpers.issuedigits(latestiss)
                                                weekiss_int = helpers.issuedigits(week['ISSUE'])
                                                logger.fdebug('comparing ' + str(latest_int) + ' to ' + str(weekiss_int))
                                                if (latest_int > weekiss_int) or (latest_int == 0 or weekiss_int == 0):
                                                    logger.fdebug(str(week['ISSUE']) + ' should not be the next issue in THIS volume of the series.')
                                                    logger.fdebug('it should be either greater than ' + str(latestiss) + ' or an issue #0')
                                                    break

                                        else:
                                            #logger.fdebug('issuedate:' + str(datevalues[0]['issuedate']))
                                            #logger.fdebug('status:' + str(datevalues[0]['status']))
                                            datestatus = datevalues[0]['status']
                                            validcheck = checkthis(datevalues[0]['issuedate'], datestatus, usedate)
                                            if validcheck == True:
                                                if datestatus != 'Downloaded' and datestatus != 'Archived':
                                                    pass
                                                else:
                                                    logger.fdebug('Issue #' + str(week['ISSUE']) + ' already downloaded.')
                                                    date_downloaded = datestatus
                                            else:
                                                if date_downloaded is None:
                                                    break

                                        otot+=1
                                        dontadd = "no"
                                        if dontadd == "no":
                                            #print (row[0], row[1], row[2])
                                            tot+=1
                                            #kp.append(row[0])
                                            #ki.append(row[1])
                                            #kc.append(comicnm)
                                            if "ANNUAL" in comicnm.upper():
                                                watchfndextra.append("annual")
                                                ComicName = str(unlines[cnt]) + " Annual"
                                            else:
                                                ComicName = str(unlines[cnt])
                                                watchfndextra.append("none")
                                            watchfnd.append(comicnm)
                                            watchfndiss.append(week['ISSUE'])
                                            ComicID = comicid[cnt]
                                            if not mylar.CV_ONLY:
                                                ComicIssue = str(watchfndiss[tot -1] + ".00")
                                            else:
                                                ComicIssue = str(watchfndiss[tot -1])
                                            ComicDate = str(week['SHIPDATE'])
                                            #ComicName = str(unlines[cnt])
                                            logger.fdebug("Watchlist hit for : " + ComicName + " ISSUE: " + str(watchfndiss[tot -1]))

                                            if futurepull is None:
                                               # here we add to comics.latest
                                                updater.latest_update(ComicID=ComicID, LatestIssue=ComicIssue, LatestDate=ComicDate)
                                                # here we add to upcoming table...
                                                statusupdate = updater.upcoming_update(ComicID=ComicID, ComicName=ComicName, IssueNumber=ComicIssue, IssueDate=ComicDate, forcecheck=forcecheck)
                                            else:
                                                # here we add to upcoming table...
                                                statusupdate = updater.upcoming_update(ComicID=ComicID, ComicName=ComicName, IssueNumber=ComicIssue, IssueDate=ComicDate, forcecheck=forcecheck, futurepull='yes', altissuenumber=altissuenum)

                                            # here we update status of weekly table...
                                            if statusupdate is not None:
                                                cstatus = statusupdate['Status']
                                                cstatusid = statusupdate['ComicID']
                                            else:
                                                cstatus = None
                                                cstatusid = None
                                            #set the variable fp to denote updating the futurepull list ONLY
                                            if futurepull is None: 
                                                fp = None
                                            else: 
                                                cstatusid = ComicID
                                                fp = "yes"

                                            if date_downloaded is None:
                                                updater.weekly_update(ComicName=week['COMIC'], IssueNumber=ComicIssue, CStatus=cstatus, CID=cstatusid, futurepull=fp, altissuenumber=altissuenum)
                                            else:
                                                updater.weekly_update(ComicName=week['COMIC'], IssueNumber=ComicIssue, CStatus=date_downloaded, CID=cstatusid, futurepull=fp, altissuenumber=altissuenum)
                                            break
                                        break
                        break
                cnt-=1
        #print ("-------------------------")
        logger.fdebug("There are " + str(otot) + " comics this week to get!")
        #print ("However I've already grabbed " + str(btotal) )
        #print ("I need to get " + str(tot) + " comic(s)!" )
        logger.info(u"Finished checking for comics on my watchlist.")
    #con.close()
    return


def check(fname, txt):
    with open(fname) as dataf:
        return any(txt in line for line in dataf)


def loaditup(comicname, comicid, issue, chktype):
    myDB = db.DBConnection()
    issue_number = helpers.issuedigits(issue)
    if chktype == 'annual':
        typedisplay = 'annual issue'
        logger.fdebug('[' + comicname + '] trying to locate ' + str(typedisplay) + ' ' + str(issue) + ' to do comparitive issue analysis for pull-list')
        issueload = myDB.action('SELECT * FROM annuals WHERE ComicID=? AND Int_IssueNumber=?', [comicid, issue_number]).fetchone()
    else:
        typedisplay = 'issue'
        logger.fdebug('[' + comicname + '] trying to locate ' + str(typedisplay) + ' ' + str(issue) + ' to do comparitive issue analysis for pull-list')
        issueload = myDB.action('SELECT * FROM issues WHERE ComicID=? AND Int_IssueNumber=?', [comicid, issue_number]).fetchone()

    if issueload is None:
        logger.fdebug('No results matched for Issue number - either this is a NEW issue with no data yet, or something is wrong')
        return 'no results'

    dataissue = []    
    releasedate = issueload['ReleaseDate']
    storedate = issueload['IssueDate']
    status = issueload['Status']

    if releasedate == '0000-00-00':
        logger.fdebug('Store date of 0000-00-00 returned for ' + str(typedisplay) + ' # ' + str(issue) + '. Refreshing series to see if valid date present')
        mismatch = 'no'
        issuerecheck = mylar.importer.addComictoDB(comicid,mismatch,calledfrom='weekly',issuechk=issue_number,issuetype=chktype)
        if issuerecheck is not None:
            for il in issuerecheck:
                #this is only one record..
                releasedate = il['IssueDate']
                storedate = il['ReleaseDate']
                status = il['Status']
            logger.fdebug('issue-recheck releasedate is : ' + str(releasedate))
            logger.fdebug('issue-recheck storedate of : ' + str(storedate))

    if releasedate is not None and releasedate != "None" and releasedate != "":
        logger.fdebug('Returning Release Date for ' + str(typedisplay) + ' # ' + str(issue) + ' of ' + str(releasedate))
        thedate = re.sub("[^0-9]", "", releasedate)  #convert date to numerics only (should be in yyyymmdd)
        #return releasedate
    else:
        logger.fdebug('Returning Publication Date for issue ' + str(typedisplay) + ' # ' + str(issue) + ' of ' + str(storedate))
        if storedate is None and storedate != "None" and storedate != "":
            logger.fdebug('no issue data available - both release date & store date. Returning no results')
            return 'no results'
        thedate = re.sub("[^0-9]", "", storedate)  #convert date to numerics only (should be in yyyymmdd)
        #return storedate

    dataissue.append({"issuedate":  thedate,
                      "status":     status})

    return dataissue

def checkthis(datecheck,datestatus,usedate):

    logger.fdebug('Now checking date comparison using an issue store date of ' + str(datecheck))
    logger.fdebug('Using a compare date (usedate) of ' + str(usedate))
    logger.fdebug('Status of ' + str(datestatus))

    if int(datecheck) >= int(usedate):
        logger.fdebug('Store Date falls within acceptable range - series MATCH')
        valid_check = True
    elif int(datecheck) < int(usedate):
        logger.fdebug('The issue date of issue was on ' + str(datecheck) + ' which is prior to ' + str(usedate))
        valid_check = False

    return valid_check
