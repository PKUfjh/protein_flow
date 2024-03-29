import os, sys
import logging
from typing import Dict, List
from pathlib import Path
from dflow.python import (
    OP,
    OPIO,
    OPIOSign,
    Artifact,
    Parameter,
    BigParameter
)
from pflow.constants import (
        gmx_conf_name,
        gmx_top_name,
        gmx_mdp_name, 
        gmx_tpr_name,
        plumed_input_name,
        plumed_output_name,
        gmx_mdrun_log,
        gmx_xtc_name,
        gmx_align_name,
        gmx_center_name
    )

from pflow.utils import run_command, set_directory, list_to_string, write_txt
from pflow.common.gromacs.trjconv import pbc_trjconv, center_trjconv, align_trjconv, begin_trjconv
from pflow.common.sampler.command import get_grompp_cmd, get_mdrun_cmd
import numpy as np
import matplotlib.pyplot as plt
import json

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=os.environ.get("LOGLEVEL", "INFO").upper(),
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


class RunLabel(OP):

    """
    In `RunLabel`, labeling processes are achieved by restrained MD simulations 
    where harmonnic restraints are exerted on collective variables.
    `RunLabel` is able to run in a standard Gromacs-PLUMED2 or Lammps-PLUMED2 env.
    """

    @classmethod
    def get_input_sign(cls):
        return OPIOSign(
            {
                "task_path": Artifact(Path),
                "forcefield": Artifact(Path, optional=True),
                "label_config": BigParameter(Dict),
                "label_cv_config":BigParameter(Dict),
                "task_name": BigParameter(str),
                "index_file": Artifact(Path, optional=True)
            }
        )

    @classmethod
    def get_output_sign(cls):
        return OPIOSign(
            {
                "plm_out": Artifact(Path, archive = None),
                "plm_fig": Artifact(Path, archive = None),
                "conf_begin": Artifact(Path, archive = None),
                "trajectory_aligned": Artifact(Path, archive = None),
                "md_log": Artifact(Path, archive = None),
                "succeeded_task_name":  Artifact(Path, optional=True, archive = None)
            }
        )

    @OP.exec_sign_check
    def execute(
        self,
        op_in: OPIO,
    ) -> OPIO:

        r"""Execute the OP.
        
        Parameters
        ----------
        op_in : dict
            Input dict with components:

            - `task_path`: (`Artifact(Path)`) A directory path containing files for Gromacs/Lammps MD simulations.
            - `label_config`: (`Dict`) Configuration of Gromacs/Lammps simulations in label steps.
            - `cv_config`: (`Dict`) Configuration of CV in MD simulations.
          
        Returns
        -------
            Output dict with components:
        
            - `forces`: (`Artifact(Path)`) mean forces value of restrained/constrained estimator.
            - `mf_info`: (`Artifact(Path)`) mean force value and std information of restrained/constrained estimator.
        """
        
        if op_in["index_file"] is None:
            index = None
        else:
            index = op_in["index_file"].name
            
        if "inputfile" in op_in["label_config"]:
            inputfile_name = op_in["label_config"]["inputfile"]
        else:
            inputfile_name = None
            
        grompp_cmd = get_grompp_cmd(
            sampler_type=op_in["label_config"]["type"],
            mdp = gmx_mdp_name,
            conf = gmx_conf_name,
            topology = gmx_top_name,
            output = gmx_tpr_name,
            index = index,
            max_warning=op_in["label_config"]["max_warning"]
        )
        run_cmd = get_mdrun_cmd(
            sampler_type=op_in["label_config"]["type"],
            tpr=gmx_tpr_name,
            plumed=plumed_input_name,
            nt=op_in["label_config"]["nt"],
            ntmpi=op_in["label_config"]["ntmpi"],
            inputfile=inputfile_name
        )

        with set_directory(op_in["task_path"]):
            if op_in["forcefield"] is not None:
                os.symlink(op_in["forcefield"], op_in["forcefield"].name)
            if op_in["index_file"] is not None:
                os.symlink(op_in["index_file"], op_in["index_file"].name)
                
            if grompp_cmd is not None:
                logger.info(list_to_string(grompp_cmd, " "))
                return_code, out, err = run_command(grompp_cmd)
                assert return_code == 0, err
                logger.info(err)
            if run_cmd is not None:
                logger.info(list_to_string(run_cmd, " "))
                return_code, out, err = run_command(run_cmd)
                assert return_code == 0, err
                logger.info(err)

            pbc_trjconv(xtc = gmx_xtc_name,output = "md_nopbc.xtc")
            align_trjconv(xtc = "md_nopbc.xtc", output_group = 1, output=gmx_align_name)
            begin_trjconv(xtc = gmx_align_name, output_group = 3)
            center_trjconv(xtc = gmx_align_name,output_group = 3, output=gmx_center_name)
            
            # set figure for plotting
            plt.figure(figsize=(8,6))
            # Load the data from the text file
            data = np.loadtxt(plumed_output_name)
            # Extract the second column
            second_column = data[:, 1]
            # Create the plot
            plt.plot(second_column)
            # Add labels and title
            plt.xlabel('Frames')
            plt.ylabel('Distance')
            plt.title('Distance during simulation')

            # Show the plot
            plt.savefig("plm.png")
            
            write_txt("task_name",op_in["task_name"])
         
        task_name_path = None   
        traj_aligned_path = None
        conf_begin_path = None
        if op_in["label_config"]["type"] == "gmx":
            mdrun_log = gmx_mdrun_log
            if os.path.exists(op_in["task_path"].joinpath(gmx_center_name)):
                traj_aligned_path = op_in["task_path"].joinpath(gmx_center_name)
            if os.path.exists(op_in["task_path"].joinpath("begin.gro")):
                conf_begin_path = op_in["task_path"].joinpath("begin.gro")

        if os.path.exists(op_in["task_path"].joinpath("task_name")):
            task_name_path = op_in["task_path"].joinpath("task_name")
        plm_out = None
        if os.path.exists(op_in["task_path"].joinpath(plumed_output_name)):
            plm_out = op_in["task_path"].joinpath(plumed_output_name)
        plm_fig = None
        if os.path.exists(op_in["task_path"].joinpath("plm.png")):
            plm_fig = op_in["task_path"].joinpath("plm.png")
            
        op_out = OPIO(
            {
                "plm_out": plm_out,
                "plm_fig": plm_fig,
                "trajectory_aligned": traj_aligned_path,
                "conf_begin": conf_begin_path,
                "md_log": op_in["task_path"].joinpath(mdrun_log),
                "succeeded_task_name": task_name_path
            }
        )
        return op_out