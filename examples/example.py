"""An example of how to utilize the package to train on energies and forces"""

from ase import Atoms
import torch
import ase
import numpy as np
import torch.nn as nn
import torch.optim as optim
from ase.calculators.emt import EMT
from amptorch.model import CustomLoss
from amptorch import AMP
from amptorch.core import AMPTorch
from amptorch.analysis import parity_plot
from amptorch.gaussian import SNN_Gaussian # simple_nn derived fingerprints
from amp.descriptor.gaussian import Gaussian # amp derived fingerprints
from ase.visualize import view
from ase.io import read

# define training images
distances = np.linspace(2, 5, 100)
label = "example"
images = []
for l in distances:
    image = Atoms(
        "CuCO",
        [
            (-l * np.sin(0.65), l * np.cos(0.65), 0),
            (0, 0, 0),
            (l * np.sin(0.65), l * np.cos(0.65), 0),
        ],
    )
    image.set_cell([10, 10, 10])
    image.wrap(pbc=True)
    image.set_calculator(EMT())
    images.append(image)

# define symmetry functions to be used
Gs = {}
Gs["G2_etas"] = np.logspace(np.log10(0.05), np.log10(5.0), num=4)
Gs["G2_rs_s"] = [0] * 4
Gs["G4_etas"] = [0.005]
Gs["G4_zetas"] = [1.0]
Gs["G4_gammas"] = [+1.0, -1]
Gs["cutoff"] = 6.5

# define the number of threads to parallelize training across
torch.set_num_threads(1)

# declare the calculator and corresponding model to be used
calc = AMP(
    model=AMPTorch(
        images,
        descriptor=SNN_Gaussian,
        Gs=Gs,
        cores=1,
        force_coefficient=0.3,
        label=label,
        save_logs=True,
    )
)
# define model settings
calc.model.device = "cpu"
calc.model.structure = [3, 10]
calc.model.val_frac = 0
calc.model.convergence = {
    "energy": 0.005,
    "force": 0.005,
    "epochs": 100,
    "early_stop": False,
}
calc.model.loader_params = {
        "batch_size": None,
        "shuffle": False,
        "num_workers": 0}
calc.model.criterion = CustomLoss
calc.model.optimizer = optim.LBFGS
calc.model.lr = 1e-2
calc.model.fine_tune = None

# train the model
calc.train(overwrite=True)
parity_plot(calc, images, data="energy", label=label)
parity_plot(calc, images, data="forces", label=label)
