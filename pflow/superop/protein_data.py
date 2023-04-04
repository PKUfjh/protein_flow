from typing import Dict, List
from copy import deepcopy
from dflow import (
    InputParameter,
    Inputs,
    InputArtifact,
    Outputs,
    OutputArtifact,
    Step,
    Steps
)
from dflow.python import(
    PythonOPTemplate,
    OP,
    Slices,
)
from pflow.utils import init_executor


class Data(Steps):
    
    r"""" Data SuperOP.
    This SuperOP transform Gromacs traj into npz files.  
    """
    def __init__(
        self,
        name: str,
        prep_data_op: OP,
        combine_data_op: OP,
        prep_data_config: Dict,
        combine_data_config: Dict,
        upload_python_package = None,
        retry_times = None
    ):

        self._input_parameters = {
            "task_name": InputParameter(type=List)
        }        
        self._input_artifacts = {
            "conf_begin": InputArtifact(),
            "trajectory_aligned": InputArtifact()
        }
        self._output_parameters = {
        }
        self._output_artifacts = {
            "combined_npz": OutputArtifact(),
        }

        super().__init__(        
                name=name,
                inputs=Inputs(
                    parameters=self._input_parameters,
                    artifacts=self._input_artifacts
                ),
                outputs=Outputs(
                    parameters=self._output_parameters,
                    artifacts=self._output_artifacts
                ),
            )
        
        step_keys = {
            "prep_data": "prep-data",
            "combine_data": "combine-data"
        }

        self = _data(
            self, 
            step_keys,
            prep_data_op,
            combine_data_op,
            prep_data_config = prep_data_config,
            combine_data_config = combine_data_config,
            upload_python_package = upload_python_package,
            retry_times = retry_times
        )            
    
    @property
    def input_parameters(self):
        return self._input_parameters

    @property
    def input_artifacts(self):
        return self._input_artifacts

    @property
    def output_parameters(self):
        return self._output_parameters

    @property
    def output_artifacts(self):
        return self._output_artifacts

    @property
    def keys(self):
        return self._keys


def _data(
        data_steps,
        step_keys,
        prep_data_op : OP,
        combine_data_op: OP,
        prep_data_config : Dict,
        combine_data_config : Dict,
        upload_python_package : str = None,
        retry_times: int = None
    ):
    prep_data_config = deepcopy(prep_data_config)
    combine_data_config = deepcopy(combine_data_config)
    prep_template_config = prep_data_config.pop('template_config')
    combine_template_config = combine_data_config.pop('template_config')
    prep_executor = init_executor(prep_data_config.pop('executor'))
    combine_executor = init_executor(combine_data_config.pop('executor'))


    prep_data = Step(
        'prep-data',
        template=PythonOPTemplate(
            prep_data_op,
            python_packages = upload_python_package,
            retry_on_transient_error = retry_times,
            slices=Slices(sub_path = True,
                input_parameter=["task_name"],
                input_artifact=["conf_begin","trajectory_aligned"],
                output_artifact=["traj_npz"]),
            **prep_template_config,
        ),
        parameters={
            "task_name": data_steps.inputs.parameters['task_name']
        },
        artifacts={
            "trajectory_aligned": data_steps.inputs.artifacts['trajectory_aligned'],
            "conf_begin": data_steps.inputs.artifacts['conf_begin']
        },
        key = step_keys['prep_data']+"-{{item.order}}",
        executor = prep_executor,
        **prep_data_config,
    )
    data_steps.add(prep_data)
    
    combine_data = Step(
        'combine-data',
        template=PythonOPTemplate(
            combine_data_op,
            python_packages = upload_python_package,
            retry_on_transient_error = retry_times,
            **combine_template_config,
        ),
        parameters={},
        artifacts={
            "traj_npz": prep_data.outputs.artifacts['traj_npz'],
        },
        key = step_keys['combine_data'],
        executor = combine_executor,
        **combine_data_config,
    )
    data_steps.add(combine_data)

    data_steps.outputs.artifacts["combined_npz"]._from = combine_data.outputs.artifacts["combined_npz"]
    
    return data_steps
