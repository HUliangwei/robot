"""Stable RLW domain vocabulary."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

class StrEnum(str, Enum):
    def __str__(self) -> str: return self.value

class JobState(StrEnum):
    PENDING="PENDING"; READY="READY"; RUNNING="RUNNING"; SUCCEEDED="SUCCEEDED"; FAILED="FAILED"; CANCELLED="CANCELLED"
class AttemptState(StrEnum):
    CREATED="CREATED"; RUNNING="RUNNING"; SUCCEEDED="SUCCEEDED"; FAILED="FAILED"; CANCELLED="CANCELLED"
class ReplicaState(StrEnum):
    MISSING="MISSING"; STAGING="STAGING"; VERIFYING="VERIFYING"; AVAILABLE="AVAILABLE"; FAILED="FAILED"; CORRUPT="CORRUPT"
class CompatibilityResult(StrEnum):
    PASS="PASS"; WARN="WARN"; FAIL="FAIL"; UNKNOWN="UNKNOWN"

@dataclass(frozen=True)
class Experiment:
    experiment_id:str; name:str; question:str=""; schema_version:str="rlw.experiment/v1"
@dataclass(frozen=True)
class Trial:
    trial_id:str; experiment_id:str; resolved_variables:Mapping[str,Any]=field(default_factory=dict); schema_version:str="rlw.trial/v1"
@dataclass(frozen=True)
class Run:
    run_id:str; trial_id:str; status:str="PENDING"; parent_run_id:str|None=None; schema_version:str="rlw.run/v1"
@dataclass(frozen=True)
class Job:
    job_id:str; run_id:str; kind:str; state:JobState=JobState.PENDING; depends_on:tuple[str,...]=(); schema_version:str="rlw.job/v1"
@dataclass(frozen=True)
class ExecutionAttempt:
    attempt_id:str; job_id:str; state:AttemptState=AttemptState.CREATED; exit_code:int|None=None; schema_version:str="rlw.execution_attempt/v1"
@dataclass(frozen=True)
class Artifact:
    artifact_id:str; kind:str; display_name:str; producer_run:str|None=None; digest:str|None=None; schema_version:str="rlw.artifact/v1"
@dataclass(frozen=True)
class ArtifactReplica:
    artifact_id:str; node_id:str; uri:str; state:ReplicaState=ReplicaState.MISSING; digest:str|None=None; size_bytes:int|None=None; persistent:bool=False; cache:bool=False; pinned:bool=False; schema_version:str="rlw.artifact_replica/v1"
@dataclass(frozen=True)
class DatasetRevision:
    dataset_id:str; revision:str; digest:str|None=None; schema_version:str="rlw.dataset_manifest/v1"
@dataclass(frozen=True)
class ProviderSpec:
    name:str; version:str|None=None; adapter_version:str="0.1"; capabilities:tuple[str,...]=(); schema_version:str="rlw.provider_spec/v1"
@dataclass(frozen=True)
class CommandSpec:
    argv:tuple[str,...]|Sequence[str]; cwd:str|None=None; env:Mapping[str,str]=field(default_factory=dict); schema_version:str="rlw.command_spec/v1"
    def normalized_argv(self)->tuple[str,...]: return tuple(str(item) for item in self.argv)
@dataclass(frozen=True)
class ResourceRequirement:
    gpu_count:int=0; gpu_ids:tuple[int,...]=(); cpu_cores:int|None=None; memory_gb:float|None=None; schema_version:str="rlw.resource_requirement/v1"
@dataclass(frozen=True)
class NodeCapability:
    node_id:str; execution:bool=True; archive:bool=False; gui:bool=True; gpu_count:int=0; metadata:Mapping[str,Any]=field(default_factory=dict); schema_version:str="rlw.node_capability/v1"
@dataclass(frozen=True)
class SecretRef:
    name:str; backend:str="environment"; schema_version:str="rlw.secret_ref/v1"
@dataclass(frozen=True)
class MetricRecord:
    name:str; value:float; namespace:str="rlw"; unit:str|None=None; direction:str|None=None; aggregation:str|None=None; scope:str|None=None; episodes:int|None=None; provider:str|None=None; definition_version:str|None=None; schema_version:str="rlw.metric_record/v1"
