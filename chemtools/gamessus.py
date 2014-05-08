
'''
Module for handling Gamess-US related jobs,:
    Gamess       : running and submitting jobs, writing inputs,
    GamessParser : parsing the log file,
    GamessReader : reading gamess bianry files.
    GamessDatParser : parsing data from the gamess PUNCH (*.dat) file
'''

from code import Code
from basisset import Basis
from molecule import Molecule
from subprocess import Popen
import numpy as np
import os
import re
import sys

# fortran modules nedded for GamessReader Class
try:
    import dictfile as df
    import twoe
except:
    pass

class Gamess(Code):

    '''Container object for Gamess-us jobs.'''

    def __init__(self, **kwargs):
        super(Gamess, self).__init__(**kwargs)

        if "version" in kwargs.items():
            self.version = kwargs["version"]

    def run_single(self, inpfile, remove_dat=True):

        '''Run a single gamess job interactively - without submitting to the
        queue.'''

        datfile = os.path.splitext(inpfile)[0] + ".dat"
        if remove_dat:
            if os.path.exists(os.path.join(self.scratch, datfile)):
                os.remove(os.path.join(self.scratch, datfile))

        out = open(self.logfile, 'w')
        process = Popen([executable, self.inputfile, version, nproc], stdout=out, stderr=out)
        process.wait()
        out.close()

    def run_startno(self, executable, version="00", nproc="1"):

        '''Run gamess calculation starting from the orbitals in the dat file.'''

        # should add checking for the existance of the .dat file before running

        startnoinput = self.write_startno_input()
        startnooutput = os.path.splitext(startnoinput)[0] + ".log"

        out = open(startnooutput, 'w')
        process = Popen([executable, startnoinput, version, nproc], stdout=out, stderr=out)
        process.wait()
        out.close()

    def submit(self):

        '''Submit a single gamess job into the queue.'''

        pass

    def write_input(self, spherical=False, core=0):

        '''Write gamess input file based on information on molecule and basis set.'''

        with open(os.path.join(self.workdir,self.template), 'r') as tmp:
            contents = tmp.read()
        contents = re.sub(r'icharg=(\d+)?', r'icharg={0:s}'.format(str(self.molecule.charge)), contents, flags=re.I)
# write also ispher variable
        contents = re.sub(r'nact=(\d+)?', r'nact={0:<d}'.format(self.norbitals(spherical)-core), contents, flags=re.I)
        contents = re.sub(r'nels=(\d+)?', r'nels={0:<d}'.format(self.molecule.nele()-core*2), contents, flags=re.I)
        contents = re.sub(r'ncore=(\d+)?', r'ncore={0:<d}'.format(core), contents, flags=re.I)
        contents = re.sub("atomsandbasis", self.get_atoms_and_basis(), contents, flags=re.I)
        inp = open(self.inputfile, 'w')
        inp.write(contents)
        inp.close()

    def write_startno_input(self, inp=None):

        '''Write gamess input file with starting orbitals from a previous run,
            stored in the self.datname file.'''

        #  TODO
        # dopisac opcjonalny parametr norb zeby moc pisac tylko podzbior
        # orbitali zamiast wszystkich

        with open(inp, 'r') as finp:
            inpcontent = finp.read()
        inpcontent = re.sub(r'scftyp=[A-Za-z]*', r'scftyp=none', inpcontent, flags=re.I)

        base = os.path.splitext(inp)[0]
        log  = base + ".log"
        dat  = base + ".dat"
        newinpfile = base + "_NO.inp"

        glp = GamessLogParser(log)

        newinp = open(newinpfile, "w")

        newinp.write(inpcontent)
        newinp.write(" $GUESS guess=moread norb={:<d} $END\n\n".format(glp.get_number_of_mos()))
        newinp.write(" $VEC\n")
        gdp = GamessDatParser(dat)
        newinp.write(gdp.get_nos())
        newinp.write(" $END\n")
        newinp.close()
        return newinpfile

    def __repr__(self):
        return "Gamess-US job object:\n\tMolecule  : {0:s}\n\tBasis     : {1:s}\n\tInput file: {2:s}".format(self.molecule.name, self.basis.name, self.inputfile)

class GamessInpParser(object):
    '''
    A class for larsing and writing gamess-us input files.
    '''

    def __init__(self, inp):
        '''
        Initialize the class.
        '''
        self.inpfile = inp

    def parse_gamess_input(contents):
        '''
        Parse gamess input file into a dictionary of dictionaries, where the
        highest level entries are gamess namelist fileds and that contain
        dictionaries of options. All key are converted to lowercase. For example if
        the following input was parsed:

        " $CONTRL scftyp=rhf units=bohr
            runtyp=energy   cityp=ormas $END
        $SYSTEM TIMLIM=1000 mwords=500 $END
        ..."

        the follwoing dictionary will be produced:

        {"$contrl" : {"scftyp" : "rhf",
                    "units"  : "bohr",
                    "runtyp" : "energy",
                    "cityp"  : "ormas"},
        "$system" : {"timlim" : "1000",
                    "mwords" : "500"},
        ...
        }
        '''

        dontparse = ["$data", "$vec", ]

        pat = re.compile(r'(?P<group>\$[a-zA-Z]{3,6})\s+(?P<entries>.*?)\$END', flags=re.S)

        dinput = {}

        iterator = pat.finditer(contents)

        for match in iterator:
            if match.group("group").lower() not in dontparse:
                dinput[match.group("group").lower()] = {}
                fields = [s.strip() for s in match.group("entries").split("\n")]
                for field in fields:
                    if not field.startswith("!"):
                        for line in field.split():
                            key, value = line.split("=")
                            dinput[match.group("group").lower()][key.lower()] = value
            elif match.group("group").lower() == "$data":
                bs = parse_basis(match.group("entries").split("\n"))
        if "$data" in [match.group("group").lower() for match in iterator]:
            return dinput, bs
        else:
            return dinput

class GamessLogParser(object):

    '''Class holding tools for parsing gamess-us log file.'''

    def __init__(self, log):
        self.logfile = log
        self.logexists()

    def logexists(self):

        '''Check if the log file exists.'''

        if os.path.exists(self.logfile):
            return True
        else:
            sys.exit("Gamess log file: {0:s} doesn't exist in {1:s}".format(
                     self.logfile, os.getcwd()))

    def terminatedOK(self):

        '''Check if a job teminated normally.'''

        patt = r'TERMINATED NORMALLY'
        compatt = re.compile(patt)
        with open(self.logfile, 'r') as log:
            lines = log.read()
        match = compatt.search(lines)
        if match:
            return True
        else:
            return False

    def get_charge(self):

        '''Get total charge.'''

        patt = r'CHARGE OF MOLECULE\s+=\s*(?P<charge>\d+)'
        compatt = re.compile(patt)
        with open(self.logfile, 'r') as log:
            lines = log.read()
        match = compatt.search(lines)
        if match:
            return int(match.group("charge"))

    def get_electrons(self):

        '''Get number of electrons.'''

        patt = r'NUMBER OF ELECTRONS\s+=\s*(?P<nele>\d+)'
        compatt = re.compile(patt)
        with open(self.logfile, 'r') as f:
            lines = f.read()
        match = compatt.search(lines)
        if match:
            return int(match.group("nele"))

    def get_homo(self):

        '''Get the orbital index of homo orbital (indexing starts from zero).'''

        if int(self.get_electrons()) % 2 == 0:
            return int(self.get_electrons())/2 - 1
        else:
            sys.exit("open shell handling not implemented")

    def get_number_of_atoms(self):

        '''Get total number of atoms from gamess log file.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        nat_re = r'TOTAL NUMBER OF ATOMS\s+=\s*(?P<nat>\d+)'
        compre   = re.compile(nat_re)
        match    = compre.search(data)
        if match:
            return int(match.group("nat"))

    def get_number_of_aos(self):

        '''Get the number of primitive cartesian gaussian basis functions from
        Gamess log file'''

        patt    = r'NUMBER OF CARTESIAN GAUSSIAN BASIS FUNCTIONS =\s*(?P<nao>\d+)'
        compatt = re.compile(patt)
        with open(self.logfile, 'r') as f:
            lines = f.read()
        match = compatt.search(lines)
        if match:
            return int(match.group("nao"))

    def get_number_of_mos(self):

        '''Get the number of molecular orbitals from Gammess log file.'''

        ispher_patt    = r'ISPHER=\s*(?P<ispher>\-?\d{1}).*'
        var_space_patt = r'.*VARIATION SPACE IS\s*(?P<nmo>\d+).*'
        c_ispher       = re.compile(ispher_patt)
        c_var_space    = re.compile(var_space_patt)

        with open(self.logfile, 'r') as log:
            lines = log.read()

        match = c_ispher.search(lines)
        if match:
            ispher = int(match.group("ispher"))

        if ispher == -1:
            return self.get_number_of_aos()
        elif ispher == 1:
            match = c_var_space.search(lines)
            if match:
                n_mo = int(match.group("nmo"))
                return n_mo
        else:
            sys.exit("wrong ispher found: {0:d}".format(ispher))

    def get_linear_deps(self):

        '''Get number of linearly dependent combinations dropped.'''

        with open(self.logfile, 'r') as log:
            lines = log.read()

        linre = re.compile(r'NUMBER OF LINEARLY DEPENDENT MOS DROPPED=\s*(\d+)')

        match = linre.search(lines)
        if match:
            return match.group(1)

    def get_scf_type(self):

        '''Get the information on SCFTYP used in the gamess job.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        scftyp_re = r'.*SCFTYP=(?P<scftyp>[A-Z]+)'
        compre   = re.compile(scftyp_re)
        match    = compre.search(data)
        if match:
            return match.group("scftyp")

    def get_cc_type(self):

        '''Get the information on CCTYP used in the gamess job.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        cctyp_re = r'.*CCTYP =(?P<cctyp>[A-Z]+)'
        compre   = re.compile(cctyp_re)
        match    = compre.search(data)
        if match:
            return match.group("cctyp")

    def get_ci_type(self):

        '''Get the information on CITYP used in the gamess job.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        cityp_re = r'.*CITYP =(?P<cityp>[A-Z]+)'
        compre   = re.compile(cityp_re)
        match    = compre.search(data)
        if match:
            return match.group("cityp")

    def get_hf_total_energy(self):

        '''Return the total HF energy.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        hfre = re.compile(r'FINAL R[O]*HF ENERGY IS\s+(?P<energy>\-?\d+\.\d+)', flags=re.M)
        match = hfre.search(data)
        if match:
            return float(match.group("energy"))

    def get_ormas_total_energy(self):

        '''Return the total ORMAS CI energy.'''

        with open(self.logfile, 'r') as log:
            data = log.read()

        orcire = re.compile(r'ORMAS CI PROPERTIES.*TOTAL ENERGY \=\s*(?P<energy>\-?\d+\.\d+).*END OF', flags=re.S)
        match = orcire.search(data)
        if match:
            return float(match.group("energy"))

    def get_ci_total_energy(self):

        '''Return the total CI energy.'''

        with open(self.logfile, 'r') as log:
            data = log.read()
        energies = re.findall(r'^\s+TOTAL ENERGY =\s*(\-?\d+\.\d+)', data,
                              re.MULTILINE)
        return float(energies[-1])

    def get_ccsd_total_energy(self):

        '''Return total CCSD energy.'''

        with open(self.logfile, 'r') as log:
            data = log.read()
        ccsdt_re = r'CCSD\s{1,4}ENERGY:\s*(\-?\d+\.\d+)'
        compre = re.compile(ccsdt_re)
        match = compre.search(data, re.MULTILINE)
        if match:
            return float(match.group(1))

    def get_ccsdt_total_energy(self):

        '''Return total CCSD(T) energy.'''

        with open(self.logfile, 'r') as log:
            data = log.read()
        ccsdt_re = r'CCSD\(T\) ENERGY:\s*(\-?\d+\.\d+)'
        compre = re.compile(ccsdt_re)
        match = compre.search(data, re.MULTILINE)
        if match:
            return float(match.group(1))

    def get_ci_ee_energy(self):
        with open(self.logfile, 'r') as log:
            data = log.read()
        energies = re.findall(r'^\s+TWO ELECTRON ENERGY =\s*(\-?\d+\.\d+)', data, re.MULTILINE)
        return float(energies[-1])

    def get_ci_oe_energy(self):
        with open(self.logfile, 'r') as log:
            data = log.read()
        energies = re.findall(r'^\s+ONE ELECTRON ENERGY =\s*(\-?\d+\.\d+)', data, re.MULTILINE)
        return float(energies[-1])

    def get_ci_nucrep_energy(self):
        with open(self.logfile, 'r') as log:
            data = log.read()
        energies = re.findall(r'^\s+NUCLEAR REPULSION ENERGY =\s*(\-?\d+\.\d+)', data, re.MULTILINE)
        return float(energies[-1])

    def get_energy_components(self, method):
        '''
        Read the summary of the energies printed in the gamess log file at the
        property section corresponding to a particular "method".
        '''

        if method.lower() in ["hf", "scf", "hfscf"]:
            if self.get_scf_type() != "NONE":
                header = 'PROPERTY VALUES FOR THE {0:<5s} SELF-CONSISTENT FIELD WAVEFUNCTION'.format(self.get_scf_type())
            else:
                sys.exit("No HF calculation was performed, check the log file once again.")
        elif method.lower() in ["ci"]:
            if self.get_ci_type().lower() in ["guga", "ormas", "fsoci"]:
                header  = '{0:<5s} CI PROPERTIES'.format(self.get_ci_type())
        else:
            sys.exit("Wrong method in <get_energy_components>: {0:s}".format(method))

        with open(self.logfile, 'r') as log:
            data = log.readlines()

        return parse_pairs(slice_after(data, header, 22))

class GamessReader(object):

    '''Class for holding method for reading gamess binary files:
        $JOB.F08 : two electron integrals over AO's,
        $JOB.F09 : two electron integrals over MO's,
        $JOB.F10 : the dictionary file with one electron integrals, orbitals etc.,
        $JOB.F15 : GUGA and ORMAS two-electron reduced density matrix,

        TODO:
        CI coefficients, and CI hamiltonian amtrix elements.'''

    def __init__(self, log):
        self.logfile    = log
        i = self.logfile.index("log")
        self.filebase   = self.logfile[:i-1]
        self.datfile    = self.filebase + ".dat"
        self.twoeaofile = self.filebase + ".F08"
        self.twoemofile = self.filebase + ".F09"
        self.dictionary = self.filebase + ".F10"
        self.rdm2file   = self.filebase + ".F15"
        self.gp         = GamessLogParser(log=self.logfile)

    def get_onee_size(self, aos=True):
        '''
        Get the size of the vector holding upper (or lower) triangle
        of a square matrix of size naos or nmos.
        '''
        if aos:
            n = self.gp.get_number_of_aos()
        else:
            n = self.gp.get_number_of_mos()
        return n*(n+1)/2

    def get_twoe_size(self):
        '''
        Get the size of the 1d vector holding upper (or lower) triangle
        of a supermatrix of size nmos (2RDM and two-electrons integrals).
        '''
        n = self.get_onee_size(aos=False)
        return n*(n+1)/2

    def read_rdm2(self, filename=None, nmo=None):

        '''Read the 2rdm from the gamess-us file'''

        # initialize numpy array to zeros
        rdm2 = np.zeros(self.get_twoe_size(), dtype=float)

        # use gamess module to read the integrals from the file -filename-
        if filename:
            if os.path.exists(filename):
                print("Reading {}".format(filename))
                twoe.integrals.readinao(rdm2, filename)
                return rdm2
            else:
                sys.exit("File '{0:s}' doesn't exist, exiting...".format(filename))
        elif os.path.exists(self.rdm2file):
            print("Reading {}".format(self.rdm2file))
            twoe.integrals.readinao(rdm2, self.rdm2file)
            return rdm2
        else:
            sys.exit("File '{0:s}' doesn't exist, exiting...".format(self.rdm2file))

    def read_twoemo(self, filename=None, nmo=None):

        '''Read the two electron integrals from the gamess-us file'''

        # initialize numpy array to zeros
        ints = np.zeros(self.get_twoe_size(), dtype=float)
        # use gamess module to read the integrals from the file -filename-
        if filename:
            if os.path.exists(filename):
                twoe.integrals.readinmo(ints, filename)
                return ints
            else:
                sys.exit("File '{0:s}' doesn't exist, exiting...".format(filename))
        elif os.path.exists(self.twoemofile):
            twoe.integrals.readinmo(ints, self.twoemofile)
            return ints
        else:
            sys.exit("File '{0:s}' doesn't exist, exiting...".format(self.twoemofile))


    def read_H(self):
        '''
        Read the bare nucleus hamiltonian integrals form section 11 of gamess-us
        dictionary file.
        '''
        vec = np.zeros(self.get_onee_size(), dtype=float)
        df.readit(self.dictionary, vec, 11)
        return vec

    def read_S(self):
        '''
        Read the overlap integrals form section 12 of gamess-us dictionary
        file.
        '''
        vec = np.zeros(self.get_onee_size(), dtype=float)
        df.readit(self.dictionary, vec, 12)
        return vec

    def read_T(self):
        '''
        Read the kinetic energy integrals form section 13 of gamess-us
        dictionary file.
        '''
        vec = np.zeros(self.get_onee_size(), dtype=float)
        df.readit(self.dictionary, vec, 13)
        return vec


    def read_occupations(self):
        '''
        Get the natural orbital occupation numbers from section 21 of the
        gamess-us dictionary file.
        '''
        vec = np.zeros(self.gp.get_number_of_mos(), dtype=float)
        df.readit(self.dictionary, vec, 21)
        return vec

    def read_mos(self):
        '''
        Read the Hartree-Fock MO's from the section 15 of the gamess dictionary
        file.
        '''

        mat = np.zeros(self.gp.get_number_of_aos()*self.gp.get_number_of_mos(), dtype=float)
        df.readit(self.dictionary, mat, 15)
        mat = mat.reshape((self.gp.get_number_of_aos(), self.gp.get_number_of_mos()), order='F')
        return mat

    def read_orbital_energies(self):
        '''
        Read orbital energies (HF) from the section 17 of the gamess dictionary
        file.
        '''

        vec = np.zeros(self.gp.get_number_of_mos(), dtype=float)
        df.readit(self.dictionary, vec, 17)
        return vec

    def read_nos(self):
        '''
        Read Natural Orbitals form section 19 of the gamess dictionary file.
        '''

        mat = np.zeros(self.gp.get_number_of_aos()*self.gp.get_number_of_mos(), dtype=float)
        df.readit(self.dictionary, mat, 19)
        mat  = mat.reshape((self.gp.get_number_of_aos(), self.gp.get_number_of_mos()), order='F')
        return mat

    def factor(i,j,k,l):
        '''
        Based on the orbitals indices return the factor that takes into account 
        the index permutational symmetry.
        '''
        if i == j and k == l and i == k:
            fijkl = 1.0
        elif i == j and k == l:
            fijkl = 2.0
        elif (i == k and j == l) or (i == j and i == k) or (j == k and j == l) or (i == j or k == l):
            fijkl = 4.0
        else:
            fijkl = 8.0
        return fijkl

# this function should be moved somewhere else

    def ijkl(self, i,j,k,l):
        '''
        Based on the four orbital indices i,j,k,l return the address
        in the 1d vector.
        '''
        ij = max(i, j)*(max(i, j) + 1)/2 + min(i, j)
        kl = max(k, l)*(max(k, l) + 1)/2 + min(k, l)
        return max(ij, kl)*(max(ij, kl) + 1)/2 + min(ij, kl)

    def print_twoe(self, twoe, nbf):
        '''Print the two-electron integrals.'''
        ij=0
        for i in xrange(nbf):
            for j in xrange(i+1):
                ij += 1
                kl = 0
                for k in xrange(nbf):
                    for l in xrange(k+1):
                        kl += 1
                        if ij >= kl:
                            if abs(twoe[self.ijkl(i,j,k,l)]) > 1.0e-10:
                                print "{0:3d}{1:3d}{2:3d}{3:3d} {4:25.14f}".format(
                                    i, j, k, l, twoe[self.ijkl(i,j,k,l)])

class GamessDatParser(object):

    def __init__(self, datfile):
        self.datfile = datfile

    def get_occupations(self):
        '''
        Parse the occupation numbers from the ASCII $JOB.dat gamess-us punch file.
        '''

        with open(self.datfile, 'r') as dat:
            data = dat.read()

        no_patt = re.compile(r'\$OCC(.*?)\$END', flags=re.DOTALL)
        match = no_patt.search(data)
        nooc = []
        if match:
            for line in match.group(1).split('\n'):
                nooc.extend([float(x) for x in line.split()])
            return np.asarray(nooc)
        else:
            sys.exit('No section with occupation numbers found.')

    def get_nos(self):
        '''
        Parse the natural orbitals from the ASCII $JOB.dat gamess-us punch file.
        '''

        with open(self.datfile, 'r') as dat:
            data = dat.read()

        no_patt = re.compile(r'NO.*\$VEC\s+\n(.*?)\$END', flags=re.DOTALL)
        match = no_patt.search(data)
        if match:
            return match.group(1)
        else:
            sys.exit('No section with natural orbitals found.')

    def parse_nos(self):
        '''
        Parse the orbitals read from the $JOB.dat file in the ASCII format into
        an 2 dimensional array.
        '''
        pass

    def parse_orbitals(orbstr, naos, nmos):
        '''
        parse gamess orbitals from a string obtained from dat file
        '''

        orblines = orbstr.lstrip("\n").split("\n")

        if naos % 5 == 0:
            nlines = naos/5
        else:
            nlines = naos/5+1
        ij = 0
        temp = []
        orbs =[]
        for i in range(0, nmos):
            coeffs = []
            for j in range(0, nlines):
                temp = []
                ij = ij + 1
                for k in range(0,5):
                    temp.append(orblines[ij][5+15*k:5+15*k+15])
                coeffs.extend(float(item) for item in temp if len(item) == 15 )
            orbs.extend([coeffs])
        return orbs

def take(seq, num):
    '''
    Iterate over a sequence "seq" "num" times and return the list of the
    elements iterated over.
    '''
    return [next(seq) for i in range(num)]

def parse_pairs(los, sep="="):
    '''
    Parse a given list of strings "los" into a dictionary based on separation
    by "sep" character and return the dictionary.
    '''
    out = []
    for line in los:
        if sep in line:
            (name, value) = line.split(sep)
            out.append((name.strip(), float(value)))
    return dict(out)

def slice_after(seq, item, num):
    '''
    Return "num" elements of a sequence "seq" present after the item "item".
    '''
    it = iter(seq)
    for element in it:
        if item in element:
            return [next(it) for i in range(num)]
