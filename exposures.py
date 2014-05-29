# S.Rodney 2014.03.04
# Reading exposure info from a pile of flt files,
# defining epochs by date and filter, and moving
# flt files into epoch subdirs for registration
# and drizzling.

def get_explist( fltlist='*fl?.fits', outroot='TARGNAME', targetradec=[None,None] ):
    """ make a list of Exposure objects for each flt file"""
    from stsci import tools
    if type(fltlist)==str :
        fltlist=tools.parseinput.parseinput(fltlist)[0]
    return( [ Exposure( fltfile, outroot=outroot, targetradec=targetradec ) for fltfile in fltlist ] )


def define_epochs( explist, epochspan=5, mjdmin=0, mjdmax=0 ):
    """
    Sort a list of flts into epochs.  Anything with MJD < mjdmin or
    MJD > mjdmax goes into epoch 00 (the template epoch).
    All other epochs are made of exposures taken within
    epochspan days of each other.

    Caution : calling this function actually updates the input explist.
    """
    import numpy as np

    if type(explist)==str :
        explist = get_explist( explist )

    mjdlist = np.array( [ exp.mjd for exp in explist ] )
    pidvisitlist = np.array( [ exp.pidvisit for exp in explist ] )
    epochlist = np.zeros( len(mjdlist) )

    thisepochmjd0 = mjdlist.min()
    thisepoch = 1
    for imjd in mjdlist.argsort() :
        thismjd = mjdlist[imjd]
        exp = explist[imjd]
        for ithisvis in np.where( pidvisitlist == pidvisitlist[imjd] )[0] :
            if exp.epoch == -1 or not exp.ontarget :
                epochlist[ ithisvis ] = -1
                explist[ ithisvis ].epoch = -1
            else :
                if (mjdmin>0) and (thismjd < mjdmin) : thisepoch=0
                elif (mjdmax>0) and (thismjd > mjdmax) : thisepoch=0
                elif thismjd > thisepochmjd0+epochspan :
                    thisepoch += 1
                    thisepochmjd0 = thismjd
                epochlist[ ithisvis ] = thisepoch
                explist[ ithisvis ].epoch = thisepoch
    # Sort the exposure list by epoch, then filter, then visit
    explist.sort( key=lambda exp: (exp.epoch, exp.filter, exp.pidvisit,
                                   exp.mjd) )
    return(explist)

def read_epochs( explist, epochlistfile ):
    """Read the epoch sorting scheme from epochlistfile, apply it to
    the Exposures in explist (i.e. update their .epoch parameters) and
    return the modified explist.

    Caution : calling this function actually updates the input explist.
    """
    from astropy.io import ascii
    epochtable = ascii.read( epochlistfile )
    rootnamelist = epochtable['rootname'].tolist()
    epochlist = epochtable['epoch']
    for exp in explist :
        try:
            iexp = rootnamelist.index(exp.rootname)
        except ValueError:
            continue
        exp.epoch = epochlist[iexp]
    # Sort the exposure list by epoch, filter, visit, and MJD
    explist.sort( key=lambda exp: (exp.epoch, exp.filter, exp.pidvisit,
                                   exp.mjd ) )
    return(explist)

def print_epochs( explist, outfile=None, verbose=True, clobber=False, onlyfilters=None, onlyepochs=None ):
    """Print summary lines for each exposure, epoch by epoch, filter by
    filter, and visit by visit.  Everything is printed to stdout and
    to the given outfile, if provided.
    """
    import os

    if outfile :
        if os.path.exists( outfile ) :
            if clobber :
                os.remove( outfile )
            else :
                print("%s exists. Not clobbering."%outfile)
                return(outfile)
        fout = open( outfile, 'a' )

    # Sort the exposure list by epoch, then filter, then visit
    explist.sort( key=lambda exp: (exp.epoch, exp.filter, exp.pidvisit,
                                   exp.mjd) )

    header = '#%9s %5s %3s %3s %6s %5s %7s '%(
            'rootname','pid','vis','exp','filter','epoch','mjd' )

    if outfile:
        print >> fout, header
    if verbose :
        print(header)
    thisepoch = explist[0].epoch
    for exp in explist :
        if onlyfilters and exp.filter not in onlyfilters :
            continue
        if onlyepochs and exp.epoch not in onlyepochs :
            continue
        if exp.epoch!=thisepoch:
            print("")
            if outfile: print>>fout,""
            thisepoch = exp.epoch
        if outfile :
            print >>fout, exp.summaryline_short
        if verbose :
            print( exp.summaryline_short )
    if outfile :
        fout.close()

def copy_to_epochdirs( explist,  onlyfilters=[], onlyepochs=[],
                       verbose=True, clobber=False ):
    """ Given a list of Exposure objects in explist, copy the flt files into
    separate epoch directories for drizzling -- limited to the Exposures that
    match the constraints in onlyfilters and onlyepochs.
    """
    import os
    import shutil
    import stat

    # file permissions for chmod ug+rw o+r
    PERMISSIONS = stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP | stat.S_IWGRP | stat.S_IROTH

    if onlyfilters :
        if type(onlyfilters)==str :
            onlyfilters = onlyfilters.lower().split(',')
        onlyfilters = [ filt[:5].lower() for filt in onlyfilters ]
    if type(onlyepochs) in [str,int,float]  :
        onlyepochs = [ int(ep) for ep in str(onlyepochs).split(',') ]


    for exp in explist :
        # only copy files for the given filter and epoch
        if exp.epoch==-1 or not exp.ontarget : continue
        if onlyfilters and exp.filter not in onlyfilters :
            continue
        if onlyepochs and exp.epoch not in onlyepochs :
            continue
        if not os.path.isdir( exp.epochdir ):
            os.makedirs( exp.epochdir )
        newfilename = os.path.join( exp.epochdir,
                                    os.path.basename(exp.filename) )
        if clobber :
            if verbose:
                print( "Wiping away existing flt file %s"%newfilename)
            if os.path.exists( newfilename ):
                os.remove( newfilename )
        if verbose : print("Copying %s ==> %s"%(exp.filename, exp.epochdir) )
        shutil.copy( exp.filepath, newfilename )
        os.chmod( newfilename, PERMISSIONS )



def checkonimage(exp,checkradec, buffer=0, verbose=False, debug=False):
    """Check if the given ra,dec falls anywhere within the
    science frame of the image that defines the given Exposure object.
    You can extend the effective size of the science frame by <buffer>
    pixels.
    """
    import pyfits
    import pywcs
    if debug : import pdb; pdb.set_trace()
    ra,dec = checkradec
    onimage = False
    if exp.header['detector'] in ['WFC','UVIS'] :
        hdulist = pyfits.open( exp.filepath )
    else : 
        hdulist = None
    for hdr in exp.headerlist :
        expwcs = pywcs.WCS( hdr, hdulist )
        ix,iy = expwcs.wcs_sky2pix( ra, dec, 0 )
        if ix<-buffer or ix>expwcs.naxis1+buffer : continue
        if iy<-buffer or iy>expwcs.naxis2+buffer : continue
        onimage=True
        break

    if verbose and not onimage :
        print("Target RA,Dec is off image %s"%(exp.filename))
    return( onimage )


class Exposure( object ): 
    """ A class for single exposure flt.fits files, used for sorting
    them into groups by epoch and band for astrodrizzling.
    """

    def __init__( self, initstr, outroot='TARGNAME',
                  targetradec=[None, None] ) :
        if initstr.endswith('.fits') :
            self.initFromFile( initstr, outroot=outroot,
                               targetradec=targetradec )
        else :
            self.initFromStr( initstr, outroot=outroot,
                              targetradec=targetradec )


    def initFromStr(self, fltstr, outroot='TARGNAME', targetradec=[None,None] ):
        """ Initialize an Exposure object from a string. Specifically,
        a single row from the _epochs.txt file.
        """

    def initFromFile(self, filename, outroot='TARGNAME', targetradec=[None,None] ):
        """ Initialize an Exposure object from an flt.fits file.
        """
        import pyfits
        import os
        from math import ceil

        self.filename = os.path.basename( filename )
        self.filepath = os.path.abspath( filename )

        self.header = pyfits.getheader( self.filepath )
        hdulist = pyfits.open(self.filepath)
        self.headerlist = []
        for hdu in hdulist :
            if hdu.name!='SCI':continue
            self.headerlist.append( hdu.header )

        if outroot=='TARGNAME' : outroot = self.header['TARGNAME']
        self.outroot = outroot

        if 'flt.fits' in self.filename : 
            self.fltsuffix = 'flt'
            self.drzsuffix = 'drz'
        elif 'flc.fits' in self.filename : 
            self.fltsuffix = 'flc'
            self.drzsuffix = 'drc'

        self.mjd = round( self.header['EXPSTART'], 2 )
        try : 
            filtername = self.header['FILTER']
        except : 
            filtername = self.header['FILTER1']
            if filtername.startswith('CLEAR') : 
                filtername = self.header['FILTER2']
        self.filtername = filtername[:5].lower()
        self.filter = self.filtername

        self.camera = self.header['INSTRUME']+'-'+self.header['DETECTOR']

        self.pid = self.header['PROPOSID']
        self.linenum = self.header['LINENUM']
        self.target = self.header['TARGNAME']

        # Visit name and exposure number (in the orbit sequence), 
        # as defined in APT
        self.visit = self.linenum.split('.')[0]
        self.pidvisit = '%i_%s'%(self.pid, self.visit)
        self.expnum = int( self.linenum.split('.')[1] )

        if self.header['PATTERN1'] == 'NONE' :
            self.dither = ceil( self.expnum / 2. )
        else : 
            self.dither = self.header['PATTSTEP']

        self.crsplit = 0
        if 'CRSPLIT' in self.header.keys():
            if self.header['CRSPLIT'] == 2 :
                if self.header['SHUTRPOS'] == 'A' :
                    self.crsplit = 1
                elif self.header['SHUTRPOS'] == 'B' :
                    self.crsplit = 2

        self.rootname = self.header['ROOTNAME']
        self.exposure_time = self.header['EXPTIME']


        # 2-digits uniquely identifying this visit and this exposure
        # within this orbit, from the HST filename
        self.viscode = self.rootname[4:6].upper()
        self.expid = self.rootname[-3:-1]

        # epoch to be defined later
        self.epoch  = 99

        # if target ra,dec provided, check that the source is on the image
        self.ontarget=True
        if targetradec[0] is not None and targetradec[1] is not None:
            if self.camera=='ACS-WFC': buffer=50
            else : buffer=20
            if not checkonimage(self,targetradec,buffer=buffer):
                self.epoch=-1
                self.ontarget = False


    @property
    def epochdir( self ):
        return( '%s.e%02i'%( self.outroot, self.epoch ) )

    @property
    def FEVgroup( self ):
        """each exposure belongs to a single 'FEV group', which comprises all
        the images from the same Filter, same Epoch, and same (pid).Visit;
        suitable for combination with astrodrizzle in the first
        (pre-registration) drizzle pass, possibly including the CR
        rejection step.
        """
        return( '%s_e%02i_%s'%( self.filter, self.epoch, self.pidvisit ) )

    @property
    def FEgroup( self ):
        """each exposure belongs to a single 'FE group', which comprises all
        the images from the same Filter and same Epoch; suitable for
        combination with astrodrizzle in the second (post-registration)
        drizzle pass.
        """
        return( '%s_e%02i'%( self.filter, self.epoch ) )
           
    @property
    def summaryline( self ) :
        import os
        return( '%s  PID %i  Visit %s Exp %s Filter %s : Epoch %02i MJD %.1f '%(
                os.path.basename(self.filename), self.pid,
                self.visit, self.expid, self.filter,
                self.epoch, self.mjd ) )

    @property
    def summaryline_short( self ) :
        return('%9s  %5i %3s %3s %6s    %02i %7.1f '%(
                self.rootname, self.pid, self.visit, self.expid, self.filter,
                self.epoch, self.mjd ) )
