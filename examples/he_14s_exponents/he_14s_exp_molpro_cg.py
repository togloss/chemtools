import pickle
from chemtools.basisopt import BSOptimizer
from chemtools.molecule import Molecule
from chemtools.molpro import Molpro
from chemtools.basisset import BasisSet

template = '''***,he
memory,100,m                            !allocate 500 MW dynamic memory
GTHRESH,THROVL=1.0e-9

%geometry

%basis

%core

{rhf; wf,2,1,0}

'''

he = Molecule(name="He", atoms=[('He',)], charge=0, multiplicity=1)

optimization = {"method"  : "CG",
      "tol"     : 1.0e-5,
      "lambda"  : 10.0,
      "jacob"   : False,
      "options" : {"maxiter" : 100, "disp" : True},
     }

mp = Molpro(
            executable="/home/lmentel/Programs/molprop_2012_1_Linux_x86_64_i8/bin/molpro",
            runopts=["-s", "-n", "1", "-d", "/home/lmentel/scratch"],
            )


exps = ( 5.34806342e+04,   1.21788142e+04,   3.25581325e+03,
         1.00473157e+03,   3.51102141e+02,   1.35742439e+02,
         5.69386800e+01,   2.51416924e+01,   1.15836670e+01,
         5.23629402e+00,   2.38685192e+00,   7.60836609e-01)

sfuncts = {'He' : [('s', 'exp', 12, exps)]}

bso = BSOptimizer(method='hf', objective='total energy', template=template, code=mp, mol=he,
                  fsopt=sfuncts, staticbs=None, core=[0,0,0,0,0,0,0,0], fname='molpro_cg.inp',
                  verbose=True, uselogs=True, optalg=optimization)


bso.run()
with open('result_cg.pkl', 'w') as fout:
    pickle.dump(bso.result, fout)

# Energy from numerical HF solution:
# total energy:   -2.861680026576101
# WTBS            -2.86167998
