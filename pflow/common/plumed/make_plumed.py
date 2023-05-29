import json
import os
import sys
import logging
import numpy as np
from typing import List, Union, Tuple, Dict, Optional, Sequence
from pflow.utils import list_to_string
from pflow.common.mol import get_dihedral_from_resid, get_distance_from_atomid
from pflow.common.plumed.plumed_constant import (
    dihedral_name,
    distance_name,
    dihedral_def_from_atoms,
    distance_def_from_atoms,
    print_def,
    moving_restraint_def
)


logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=os.environ.get("LOGLEVEL", "INFO").upper(),
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


angle_id = {
    "phi": 0,
    "psi": 1
}


def make_restraint(
        name: str,
        arg: str,
        kappa: Union[str, int, float],
        step: Union[str, int, float],
        nsteps: Union[str, int, float],
        at: Union[str, int, float],
        final: Union[str, int, float]
    ):
    return moving_restraint_def.format(
                name = name,
                arg = arg,
                step0 = 0,
                at0 = at,
                kappa0 = kappa,
                step1 = step,
                at1 = final,
                kappa1 = kappa,
                step2 = nsteps,
                at2 = final,
                kappa2 = kappa
            )

def make_moving_restraint_list(
        cv_list: List[str],
        kappa: List[Union[int, float, str]],
        step: List[Union[int, float, str]],
        nsteps: Union[int, float, str],
        at: List[Union[int, float, str]],
        final: List[Union[int, float, str]]
    ) -> Tuple[List, List]:
    print(at)
    res_names = []
    res_list = []
    assert len(cv_list) == len(kappa), "Make sure `kappa` and `cv_names` have the same length."
    assert len(cv_list) == len(at), "Make sure `at` and `cv_names` have the same length."
    for idx, cv_print in enumerate(cv_list):
        res_name = "res-" + cv_print
        res_names.append(res_name)
        res_list.append(make_restraint(res_name, cv_print, kappa[idx], step[idx], nsteps,at[idx], final[idx]))
    return res_list, res_names


def make_print_bias(
        name_list,
        stride,
        file_name
    ) -> str:
    return print_def.format(
        stride = stride,
        arg = list_to_string(name_list, ","),
        file = file_name
    )

def make_print(
        name_list,
        stride,
        file_name
    ) -> str:
    return print_def.format(
        stride = stride,
        arg = list_to_string(name_list, ","),
        file = file_name
    )


def make_wholemolecules(atom_index):
    arg_list = list_to_string(atom_index, ",")
    return ("WHOLEMOLECULES" + " " +
            "ENTITY0=" + arg_list +
            "\n")


def user_plumed_def(cv_file, pstride, pfile):
    logger.info("Custom CVs are created from plumed files.")
    ret = ""
    cv_names = []
    print_content = None
    print("cv_file name",cv_file)
    with open(cv_file, 'r') as fp:
        for line in fp.readlines():
            if ("PRINT" in line) and ("#" not in line):
                print_content = line + "\n"
                cv_names = line.split()[2].split("=")[1].split(",")
                break
            ret += line
    if ret == "" or cv_names == []:
        raise RuntimeError("Invalid customed plumed files.")
    if print_content is not None:
        assert len(print_content.split(",")) == len(cv_names), "There are {} CVs defined in the plumed file, while {} CVs are printed.".format(len(cv_names), len(print_content.split(",")) )
        print_content_list = print_content.split()
        print_content_list[-1] = "FILE={}".format(pfile)
        print_content_list[1] = "STRIDE={}".format(str(pstride))
        print_content = " ".join(print_content_list)
    return ret, cv_names, print_content


def make_torsion(
        name: str,
        atom_list: List[Union[int, str]]
    ) -> str:
    assert len(atom_list) == 4, f"Make sure dihedral angle defined by 4 atoms, not {len(atom_list)}."
    return dihedral_def_from_atoms.format(
        name = name,
        a1 = atom_list[0], a2 = atom_list[1],
        a3 = atom_list[2], a4 = atom_list[3],
    )

def make_distance(
        name: str,
        atom_list: List[Union[int, str]]
    ) -> str:
    assert len(atom_list) == 2, f"Make sure distance defined by 2 atoms, not {len(atom_list)}."
    return distance_def_from_atoms.format(
        name = name,
        a1 = atom_list[0], a2 = atom_list[1]
    )


def make_torsion_name(resid: int, angid: int):
    return dihedral_name.format(
        resid = resid,
        angid = angid
    )

def make_distance_name(atomids: list):
    return distance_name.format(
    atomid1 = int(atomids[0]),
    atomid2 = int(atomids[1])
    )

def make_torsion_list(
        dihedral_info: Dict,
    ) -> Tuple[List, List]:
    torsion_list = []
    torsion_name_list = []
    for resid in dihedral_info.keys():
        for ang in dihedral_info[resid].keys():
            torsion_name = make_torsion_name(resid=resid, angid = angle_id[ang])
            torsion_name_list.append(torsion_name)
            torsion_list.append(make_torsion(
                name = torsion_name,
                atom_list=list(dihedral_info[resid][ang])
            ))
    return torsion_list, torsion_name_list

def make_distance_list(
        distance_info: Dict,
    ) -> Tuple[List, List]:
    distance_list = []
    distance_name_list = []
    for atomids in distance_info.keys():
        dis = distance_info[atomids]
        atom_list = atomids.split(" ")
        distance_name = make_distance_name(atomids=atom_list)
        distance_name_list.append(distance_name)
        distance_list.append(make_distance(
            name = distance_name,
            atom_list=atom_list)
        )
    return distance_list, distance_name_list

def make_torsion_list_from_file(
        file_path: str,
        selected_resid: List[int]
    ) -> Tuple[List, List]:
    cv_info = get_dihedral_from_resid( file_path, selected_resid)
    logger.info("Create CVs (torsion) from selected residue ids.")
    assert len(cv_info.keys()) > 0, "No valid CVs created."
    return make_torsion_list(cv_info)

def make_distance_list_from_file(
        file_path: str,
        selected_atomid: List[int]
    ) -> Tuple[List, List]:
    cv_info = get_distance_from_atomid(file_path, selected_atomid)
    logger.info("Create CVs (distance) from selected atom ids.")
    assert len(cv_info.keys()) > 0, "No valid CVs created."
    return make_distance_list(cv_info)

def make_restraint_plumed(
        conf: Optional[str] = None,
        cv_file: Optional[List[str]] = None,
        selected_resid: Optional[List[int]] = None,
        selected_atomid: Optional[List[int]] = None,
        kappa: Union[int, float, Sequence, np.ndarray] = 0.5,
        step: Union[int, float, Sequence, np.ndarray] = 500000,
        nsteps: Union[int, float, Sequence, np.ndarray] = 500000,
        at: Union[int, float, Sequence, np.ndarray] = 1.0,
        final: Union[int, float, Sequence, np.ndarray] = 10.0,
        stride: int = 100,
        output: str = "plm.out",
        mode: str = "torsion"
    ):
    content_list = []
    if mode == "torsion":
        cv_content_list, cv_name_list = \
            make_torsion_list_from_file(conf, selected_resid)
        content_list += cv_content_list
    elif mode == "distance":
        cv_content_list, cv_name_list = \
            make_distance_list_from_file(conf, selected_atomid)
        content_list += cv_content_list
    elif mode == "custom":
        for cv_file_ in cv_file:
            if not os.path.basename(cv_file_).endswith("pdb"):
                ret, cv_name_list, _ = user_plumed_def(cv_file_, stride, output)
        content_list.append(ret)
    else:
        raise RuntimeError("Unknown mode for making plumed files.")

    if isinstance(kappa, int) or isinstance(kappa, float):
        kappa = [kappa for _ in range(len(cv_name_list))]
    if isinstance(at, int) or isinstance(at, float):
        at = [at for _ in range(len(cv_name_list))]
        
    res_list, res_names = make_moving_restraint_list(
        cv_name_list, kappa, step, nsteps, at, final
    )
    print("res_names", res_names)
    content_list += res_list
    cv_name_list.append(res_names[0]+".force2")
    content_list.append(make_print(cv_name_list, stride, output))
    return list_to_string(content_list, split_sign="\n")


def make_plain_plumed(
        conf: Optional[str] = None,
        cv_file: Optional[List[str]] = None,
        selected_resid: Optional[List[int]] = None,
        selected_atomid: Optional[List[int]] = None,
        stride: int = 100,
        output: str = "plm.out",
        mode: str = "torsion"
    ):
    content_list = []
    if mode == "torsion":
        cv_content_list, cv_name_list = \
            make_torsion_list_from_file(conf, selected_resid)
        content_list += cv_content_list
    elif mode == "distance":
        cv_content_list, cv_name_list = \
            make_distance_list_from_file(conf, selected_atomid)
        content_list += cv_content_list
    elif mode == "custom":
        for cv_file_ in cv_file:
            if not os.path.basename(cv_file_).endswith("pdb"):
                ret, cv_name_list, _ = user_plumed_def(cv_file_, stride, output)
        content_list.append(ret)
    else:
        raise RuntimeError("Unknown mode for making plumed files.")
    content_list.append(make_print_bias(cv_name_list, stride, output))
    return list_to_string(content_list, split_sign="\n")


def get_cv_name(
        conf: Optional[str] = None,
        cv_file: Optional[List[str]] = None,
        selected_resid: Optional[List[int]] = None,
        selected_atomid: Optional[List[int]] = None,
        stride: int = 100,
        mode: str = "torsion"
    ):
    if mode == "torsion":
        _, cv_name_list = \
            make_torsion_list_from_file(conf, selected_resid)
    elif mode == "distance":
        _, cv_name_list = make_distance_list_from_file(conf, selected_atomid)
    elif mode == "custom":
        for cv_file_ in cv_file:
            if not os.path.basename(cv_file_).endswith("pdb"):
                _, cv_name_list, _ = user_plumed_def(cv_file_, stride, "test.out")
    else:
        raise RuntimeError("Unknown mode for making plumed files.")
    return cv_name_list
